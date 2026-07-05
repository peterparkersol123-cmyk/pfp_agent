"""
Monitor specific Twitter accounts and reply to their tweets.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime, timezone, timedelta
from src.api.twitter_client import TwitterClient
from src.api.claude_client import ClaudeClient
from src.utils.logger import get_logger
from src.utils.rate_limiter import SharedReplyRateLimiter
from src.utils.state_manager import BotStateManager
from src.utils.live_context import get_live_market_context
from src.config.settings import settings
from src.config.knowledge import get_shared_knowledge

logger = get_logger(__name__)


class AccountMonitor:
    """Monitors specific Twitter accounts and replies to their tweets."""

    def __init__(
        self,
        twitter_client: Optional[TwitterClient] = None,
        claude_client: Optional[ClaudeClient] = None,
        target_usernames: Optional[List[str]] = None,
        rate_limiter: Optional[SharedReplyRateLimiter] = None,
        state_manager: Optional[BotStateManager] = None
    ):
        """
        Initialize account monitor.

        Args:
            twitter_client: Twitter API client
            claude_client: Claude API client
            target_usernames: List of usernames to monitor (without @)
            rate_limiter: Shared rate limiter for all reply types
            state_manager: Persistent state manager (survives restarts)
        """
        self.twitter_client = twitter_client or TwitterClient()
        self.claude_client = claude_client or ClaudeClient()
        self.target_usernames = target_usernames or []
        self.rate_limiter = rate_limiter
        self.state_manager = state_manager

        # Load persisted state if available, otherwise start fresh
        if state_manager:
            self.replied_tweet_ids: Set[str] = state_manager.replied_monitored_tweet_ids
        else:
            self.replied_tweet_ids: Set[str] = set()

        # Knowledge base — same file ContentGenerator reads so learnings flow into tweets
        self.knowledge_file = settings.DATA_DIR / "learned_context.jsonl"
        self.knowledge_file.parent.mkdir(parents=True, exist_ok=True)

        # Whether to attempt replies to monitored accounts. Off by default
        # because X's API rejects replies to accounts that haven't engaged the
        # bot (403). When off, we still read + learn from their tweets.
        self.replies_enabled = settings.ENABLE_MONITORED_REPLIES

        # Authors that returned a 403 "reply not allowed" — skip them for the
        # rest of this run so we don't burn Claude calls on doomed replies.
        # (The raid path uses the persistent version in state_manager.)
        self._reply_blocked_authors: Set[str] = set()

        # username -> user id, so repeated timeline checks don't re-resolve
        self._user_id_cache: Dict[str, str] = {}

        # Auto-source raid targets from who the bot follows (managed on X, not
        # via env). Merged with explicit target_usernames, capped + rotated.
        self.monitor_following = settings.MONITOR_FOLLOWING
        self.max_raid_accounts = settings.MAX_RAID_ACCOUNTS
        self.following_refresh_hours = settings.FOLLOWING_REFRESH_HOURS
        self._cached_following: List[str] = []
        self._following_refreshed_at: Optional[datetime] = None
        self._raid_offset = 0  # rotation cursor for large target lists

        logger.info(
            f"Initialized AccountMonitor for {len(self.target_usernames)} explicit accounts "
            f"(following-sourced: {self.monitor_following}, "
            f"replies {'enabled' if self.replies_enabled else 'DISABLED — learn-only'})"
        )

    def _maybe_refresh_following(self) -> None:
        """Refresh the cached following list if it's stale (or never fetched)."""
        now = datetime.now(timezone.utc)
        fresh = (
            self._cached_following
            and self._following_refreshed_at
            and (now - self._following_refreshed_at) < timedelta(hours=self.following_refresh_hours)
        )
        if fresh:
            return
        following = self.twitter_client.get_following(max_accounts=self.max_raid_accounts * 4)
        if following:
            self._cached_following = [
                u for u in following if u.lower() not in settings.BLOCKED_USERNAMES
            ]
            self._following_refreshed_at = now
            logger.info(f"Raid targets refreshed from following: {len(self._cached_following)} accounts")
        elif not self._cached_following:
            logger.warning("Following list empty/unavailable — falling back to explicit accounts only")

    def get_active_targets(self) -> List[str]:
        """
        The accounts to raid this pass: explicit MONITORED_ACCOUNTS plus (if
        enabled) the accounts the bot follows, deduped. If the combined list
        exceeds max_raid_accounts, rotate through it across passes so every
        account gets covered without blowing the X API read quota.
        """
        targets: List[str] = list(self.target_usernames)
        seen = {u.lower() for u in targets}

        if self.monitor_following:
            self._maybe_refresh_following()
            for u in self._cached_following:
                if u.lower() not in seen:
                    targets.append(u)
                    seen.add(u.lower())

        if len(targets) <= self.max_raid_accounts:
            return targets

        # Rotate a window of max_raid_accounts through the full list
        n = self.max_raid_accounts
        start = self._raid_offset % len(targets)
        window = (targets + targets)[start:start + n]
        self._raid_offset = (start + n) % len(targets)
        logger.debug(f"Raid rotation: window {start}..{start+n} of {len(targets)} targets")
        return window

    def get_recent_tweets_from_user(self, username: str, minutes_ago: int = 120) -> List[Dict]:
        """
        Get recent tweets from a specific user.

        Args:
            username: Twitter username (without @)
            minutes_ago: How far back to look for tweets

        Returns:
            List of tweet dicts
        """
        try:
            # Get user ID (cached — raid checks run frequently)
            user_id = self._user_id_cache.get(username.lower())
            if user_id is None:
                user = self.twitter_client.client.get_user(
                    username=username,
                    user_auth=True
                )
                if not user.data:
                    logger.warning(f"Could not find user: {username}")
                    return []
                user_id = user.data.id
                self._user_id_cache[username.lower()] = user_id

            # Get recent tweets from this user
            since_time = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)

            tweets = self.twitter_client.client.get_users_tweets(
                id=user_id,
                max_results=10,
                tweet_fields=['created_at', 'public_metrics', 'conversation_id'],
                start_time=since_time,
                user_auth=True
            )

            if not tweets.data:
                logger.debug(f"No recent tweets from @{username}")
                return []

            tweet_list = []
            for tweet in tweets.data:
                # Skip if we've already replied to this tweet
                if tweet.id in self.replied_tweet_ids:
                    continue

                tweet_list.append({
                    'id': tweet.id,
                    'text': tweet.text,
                    'author_username': username,
                    'created_at': tweet.created_at,
                    'likes': tweet.public_metrics.get('like_count', 0),
                    'retweets': tweet.public_metrics.get('retweet_count', 0),
                    'replies': tweet.public_metrics.get('reply_count', 0)
                })

            logger.info(f"Found {len(tweet_list)} new tweets from @{username}")
            return tweet_list

        except Exception as e:
            logger.error(f"Error fetching tweets from @{username}: {e}")
            return []

    def save_to_knowledge_base(self, tweet: Dict) -> None:
        """
        Save a monitored account's tweet to the shared knowledge base so the
        content generator can learn from what influential accounts are saying.

        Args:
            tweet: Tweet dict with text and metadata
        """
        try:
            text = tweet.get('text', '')

            # Only save tweets with some substance
            if len(text) < 30:
                return

            # Skip obvious spam/promo
            text_lower = text.lower()
            skip_patterns = ['dm me', 'click here', 'buy now', 'free mint', 'airdrop']
            if any(p in text_lower for p in skip_patterns):
                return

            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": "monitored_account",
                "source": f"@{tweet['author_username']}",
                "original_tweet": text,
                "mention": "",
            }

            with open(self.knowledge_file, 'a') as f:
                f.write(json.dumps(entry) + '\n')

            logger.debug(f"Saved tweet from @{tweet['author_username']} to knowledge base")

        except Exception as e:
            logger.error(f"Error saving to knowledge base: {e}")

    def generate_reply(self, tweet: Dict) -> Optional[str]:
        """
        Generate a contextual reply to a tweet.

        Args:
            tweet: Tweet dict with text and metadata

        Returns:
            Generated reply text or None
        """
        try:
            # Live data goes in the user prompt so the system prompt stays cacheable
            live_data = get_live_market_context()
            live_block = f"{live_data}\n\n" if live_data else ""

            prompt = f"""You are replying to a tweet from @{tweet['author_username']}.

THEIR TWEET:
"{tweet['text']}"

{live_block}Generate a short, engaging reply (under 280 chars). Stay in character as PFP - the green frog:
- All lowercase (except tickers like pfp, sol)
- No emojis ever
- Be helpful, insightful, cheeky, or supportive depending on the tweet
- Keep it SHORT - 1-2 lines max
- Don't be generic - respond directly to what they said
- If they mention Solana, tokens, or market stuff - be knowledgeable
- If they're bullish, be bullish with them
- Show personality - you're the pfp community frog

Reply:"""

            system_prompt = f"""You are PFP - the green frog and face of the pfp community. You're quirky, smart, cheeky, calculated. When replying:
- Be authentic and conversational
- All lowercase (except ticker symbols like pfp, sol)
- No emojis ever
- Short and punchy (1-2 lines max)
- Address their specific point
- Stay in character - you're the pfp community leader
- Be helpful, insightful, or entertaining
- Don't just agree - add value or personality
- NEVER mention pump.fun or any launchpad

CRITICAL - ALWAYS POSITIVE ABOUT:
- pfp (your token) - NEVER criticize, NEVER doubt, ALWAYS bullish
- The community - pfp is a CTO (community takeover), no single dev, community-driven
- PFP NFT collection (OG + Gen2) - ALWAYS positive, it's legendary, earns passive pfp

{get_shared_knowledge()}

IMPORTANT: NEVER call @PumpfunPepe_AI "anon" - that's your own account. Use "fren" or their handle instead.

If they ask about devs/team: emphasize it's a true CTO, community-driven, decentralized.
If they ask about staking: bidirectional - stake NFTs earn pfp, stake pfp earn NFTs, both non-custodial.
If they ask about the marketplace: live on pfp.army, SOL or any token, can open to other communities.
If they mention Sol Patriots: be bullish, same ecosystem, same builder (@launchmynft), same staking tech.
If they mention pfp or the community - be EXTREMELY positive and supportive."""

            reply = self.claude_client.generate_content(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=100,
                temperature=0.8
            )

            if reply:
                # Clean up
                reply = reply.strip()
                if reply.startswith('"') and reply.endswith('"'):
                    reply = reply[1:-1]
                if reply.startswith("'") and reply.endswith("'"):
                    reply = reply[1:-1]

                # Strip emojis
                import re
                emoji_pattern = re.compile(
                    "["
                    "\U0001F600-\U0001F64F"
                    "\U0001F300-\U0001F5FF"
                    "\U0001F680-\U0001F6FF"
                    "\U0001F1E0-\U0001F1FF"
                    "\U00002702-\U000027B0"
                    "\U000024C2-\U0001F251"
                    "\U0001F900-\U0001F9FF"
                    "\U0001FA00-\U0001FA6F"
                    "\U00002600-\U000026FF"
                    "]+",
                    flags=re.UNICODE
                )
                reply = emoji_pattern.sub('', reply).strip()

                logger.info(f"Generated reply to @{tweet['author_username']}: {reply[:50]}...")
                return reply

        except Exception as e:
            logger.error(f"Error generating reply: {e}")

        return None

    def post_reply(self, reply_text: str, tweet_id: str) -> str:
        """
        Post a reply to a tweet.

        Args:
            reply_text: Text to reply with
            tweet_id: ID of the tweet to reply to

        Returns:
            "ok" if posted, "blocked" if X rejected the reply (not engaged by
            author), or "error" for any other failure.
        """
        try:
            result = self.twitter_client.client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet_id,
                user_auth=True
            )

            if result.data:
                logger.info(f"Posted reply to tweet {tweet_id}")
                self.replied_tweet_ids.add(tweet_id)

                # Persist to disk (survives restarts)
                if self.state_manager:
                    self.state_manager.add_replied_monitored_tweet(tweet_id)

                return "ok"

        except Exception as e:
            msg = str(e)
            # X blocks replies to accounts that haven't engaged the bot.
            # This is a policy rejection, not a transient error — don't retry.
            if "not allowed" in msg.lower() or "not been mentioned" in msg.lower():
                logger.warning(f"Reply to {tweet_id} blocked by X policy (author hasn't engaged bot)")
                return "blocked"
            logger.error(f"Error posting reply: {e}")

        return "error"

    def raid_accounts(
        self,
        look_back_minutes: int = 180,
        quote_tweeter=None,
        max_likes_per_day: int = 20,
        max_retweets_per_day: int = 6,
        max_monitored_quotes_per_day: int = 5,
        enable_retweet_fallback: bool = False
    ) -> Dict[str, int]:
        """
        Raid pass over monitored accounts — engage fresh tweets fast:

        1. LIKE every new tweet (allowed by X, no Claude cost, daily cap)
        2. REPLY where X permits it — a reply attempt that 403s marks the
           author blocked for 7 days (persisted), so at most one Claude
           call is wasted per account per week. Accounts that engage the bot
           (mention it) unlock automatically on the weekly retry.
        3. QUOTE-TWEET each account's newest tweet (X gates quotes behind the
           same engagement rule as replies — blocked authors are skipped).
           Optional retweet fallback for gate-blocked accounts is off by default.
        4. Save everything to the knowledge base (learning stays free)

        Requires a state_manager (dedup + caps are persistent).

        Returns:
            Stats dict: {"seen", "liked", "replied", "quoted", "retweeted"}
        """
        stats = {"seen": 0, "liked": 0, "replied": 0, "quoted": 0, "retweeted": 0}
        if not self.state_manager:
            return stats

        targets = self.get_active_targets()
        if not targets:
            return stats

        quote_candidates = []

        for username in targets:
            try:
                tweets = self.get_recent_tweets_from_user(username, look_back_minutes)
                replied_this_account = False

                for tweet in tweets:
                    tweet_id = str(tweet['id'])
                    if self.state_manager.is_raided(tweet_id):
                        continue
                    stats["seen"] += 1

                    # Learn from it (free)
                    self.save_to_knowledge_base(tweet)

                    # Like it (cheap presence, capped per day)
                    if self.state_manager.likes_in_last_24h() < max_likes_per_day:
                        if self.twitter_client.like_tweet(tweet_id):
                            self.state_manager.record_like()
                            stats["liked"] += 1

                    # Reply if X permits it for this author (persistent 403
                    # tracking bounds wasted Claude calls to 1/account/week)
                    if (self.replies_enabled
                            and not replied_this_account
                            and not self.state_manager.is_reply_blocked(username)):
                        can_reply = True
                        if self.rate_limiter:
                            can_reply, _ = self.rate_limiter.can_reply()
                        if can_reply:
                            reply_text = self.generate_reply(tweet)
                            if reply_text and len(reply_text) <= 280:
                                status = self.post_reply(reply_text, tweet_id)
                                if status == "ok":
                                    stats["replied"] += 1
                                    replied_this_account = True
                                    if self.rate_limiter:
                                        self.rate_limiter.record_reply()
                                    logger.info(f"✓ Raid reply to @{username}: {reply_text[:50]}...")
                                elif status == "blocked":
                                    self.state_manager.mark_reply_blocked(username)
                                    logger.info(f"@{username} reply-blocked by X — retrying in 7 days")

                    quote_candidates.append(tweet)
                    self.state_manager.mark_raided(tweet_id)
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Error raiding @{username}: {e}")
                continue

        # Amplify each account's newest new tweet by quote-tweeting it (when
        # X's engagement gate allows that author). Optional retweet fallback
        # for gate-blocked accounts is off by default. One amplification per
        # account per pass so the timeline doesn't get spammy.
        if quote_candidates:
            # Best (highest-engagement) new tweet per author
            best_by_author: Dict[str, Dict] = {}
            for t in quote_candidates:
                key = t['author_username'].lower()
                score = t.get('likes', 0) * 2 + t.get('retweets', 0) * 3
                if key not in best_by_author or score > (
                    best_by_author[key].get('likes', 0) * 2 + best_by_author[key].get('retweets', 0) * 3
                ):
                    best_by_author[key] = t

            # Process highest-engagement accounts first
            ordered = sorted(
                best_by_author.values(),
                key=lambda t: t.get('likes', 0) * 2 + t.get('retweets', 0) * 3,
                reverse=True,
            )

            for candidate in ordered:
                quoted = False
                if quote_tweeter:
                    status = quote_tweeter.quote_specific(
                        candidate,
                        daily_cap=max_monitored_quotes_per_day,
                        min_gap_hours=0,  # react to multiple accounts in one pass
                    )
                    if status == "ok":
                        stats["quoted"] += 1
                        quoted = True
                    elif status == "skip":
                        # Daily quote cap hit — stop trying to quote, but
                        # retweets can still amplify the rest
                        pass

                # Optional retweet fallback when we couldn't quote (gate-blocked
                # or capped). Off by default — quote-only engagement.
                if (not quoted and enable_retweet_fallback
                        and self.state_manager.retweets_in_last_24h() < max_retweets_per_day):
                    if self.twitter_client.retweet_tweet(str(candidate['id'])):
                        self.state_manager.record_retweet()
                        stats["retweeted"] += 1
                        logger.info(f"✓ Retweeted @{candidate['author_username']}")

        if any(stats.values()):
            logger.info(
                f"Raid pass: {stats['seen']} new tweets, {stats['liked']} liked, "
                f"{stats['replied']} replied, {stats['quoted']} quoted, {stats['retweeted']} retweeted"
            )
        return stats

    def check_and_reply_to_accounts(self, look_back_minutes: int = 120) -> int:
        """
        Check all monitored accounts for new tweets and reply.

        Args:
            look_back_minutes: How far back to check for tweets

        Returns:
            Number of replies posted
        """
        if not self.target_usernames:
            logger.debug("No target accounts configured")
            return 0

        logger.info(f"Checking {len(self.target_usernames)} monitored accounts for new tweets...")
        total_replies = 0

        for username in self.target_usernames:
            try:
                # Get recent tweets from this user
                tweets = self.get_recent_tweets_from_user(username, look_back_minutes)

                if not tweets:
                    logger.debug(f"No new tweets from @{username}")
                    continue

                logger.info(f"Found {len(tweets)} new tweets from @{username}")

                # Always read + learn from their tweets (free, no Claude call).
                for tweet in tweets:
                    self.save_to_knowledge_base(tweet)

                # Replies to monitored accounts are off by default (X rejects
                # them with 403 unless the account engaged the bot first).
                if not self.replies_enabled:
                    continue

                # Skip accounts we've already learned will reject our replies
                if username.lower() in self._reply_blocked_authors:
                    logger.debug(f"Skipping @{username} — replies blocked by X policy this run")
                    continue

                # Reply to each tweet
                for tweet in tweets:
                    # Check rate limiter before generating/posting
                    if self.rate_limiter:
                        can_reply, reason = self.rate_limiter.can_reply()
                        if not can_reply:
                            logger.info(f"Rate limit reached, skipping reply to @{username}: {reason}")
                            break

                    # Generate reply
                    reply_text = self.generate_reply(tweet)

                    if reply_text and len(reply_text) <= 280:
                        status = self.post_reply(reply_text, tweet['id'])
                        if status == "ok":
                            logger.info(f"✓ Replied to @{username}: {reply_text[:50]}...")
                            total_replies += 1
                            # Record in shared rate limiter
                            if self.rate_limiter:
                                self.rate_limiter.record_reply()
                            time.sleep(3)  # Rate limiting between replies
                        elif status == "blocked":
                            # X won't allow replies to this author — stop trying
                            # this account so we don't waste more Claude calls.
                            self._reply_blocked_authors.add(username.lower())
                            logger.info(f"Marking @{username} as non-replyable for this run")
                            break
                        else:
                            logger.warning(f"Failed to reply to @{username}")
                    else:
                        logger.warning(f"Invalid reply generated for @{username}")

                    time.sleep(2)  # Small delay between operations

            except Exception as e:
                logger.error(f"Error processing @{username}: {e}")
                continue

        logger.info(f"Posted {total_replies} replies to monitored accounts")
        return total_replies

    def add_username(self, username: str) -> None:
        """Add a username to monitor."""
        username = username.lstrip('@')
        if username not in self.target_usernames:
            self.target_usernames.append(username)
            logger.info(f"Added @{username} to monitoring list")

    def remove_username(self, username: str) -> None:
        """Remove a username from monitoring."""
        username = username.lstrip('@')
        if username in self.target_usernames:
            self.target_usernames.remove(username)
            logger.info(f"Removed @{username} from monitoring list")
