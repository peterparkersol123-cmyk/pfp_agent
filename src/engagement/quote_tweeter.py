"""
Proactive quote-tweet engine.

X's API blocks replying to accounts that haven't engaged the bot — but
quote tweets have no such restriction. This module searches X for
high-engagement tweets in the bot's niche (pfp / Solana memecoin CT) and
quote-tweets the best one with an in-character take. That's the bot's only
channel for reaching audiences beyond its own followers.

Cost design:
- One search read per check (search is skipped entirely when the daily
  quota is used up)
- One Claude call only when a candidate is actually selected
- Hard caps: MAX_QUOTES_PER_DAY (default 2), minimum 4h gap between quotes
- Dedup: never quote the same tweet twice, never quote the same author
  twice in 24h
"""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# A single tweet must clear these bars to be worth quoting
MIN_LIKES = 10
MIN_AUTHOR_FOLLOWERS = 300
MIN_TEXT_LENGTH = 40
MIN_GAP_HOURS = 4

DEFAULT_SEARCH_QUERY = (
    '("pump.fun pepe" OR "$PFP" OR "sol patriots" OR "solana memecoin") '
    '-is:retweet -is:reply -is:quote lang:en'
)

SPAM_MARKERS = [
    "dm me", "click here", "buy now", "airdrop", "free mint", "presale",
    "giveaway", "whitelist", "t.me/", "discord.gg", "guaranteed",
]


class QuoteTweeter:
    """Finds and quote-tweets high-signal tweets in the bot's niche."""

    def __init__(self, twitter_client, generator, state_manager, max_per_day: int = 2):
        self.twitter_client = twitter_client
        self.generator = generator
        self.state_manager = state_manager
        self.max_per_day = max_per_day
        self.search_query = os.getenv("QUOTE_SEARCH_QUERY", DEFAULT_SEARCH_QUERY)
        self._bot_user_id = None
        logger.info(f"Initialized QuoteTweeter (max {max_per_day}/day)")

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _can_quote_now(self) -> bool:
        recent = self.state_manager.quotes_in_last_hours(24)
        if len(recent) >= self.max_per_day:
            logger.debug("Quote quota reached for the last 24h")
            return False
        if recent:
            try:
                last = max(datetime.fromisoformat(q["at"]) for q in recent)
                gap_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
                if gap_hours < MIN_GAP_HOURS:
                    logger.debug(f"Quote min gap not elapsed ({gap_hours:.1f}h < {MIN_GAP_HOURS}h)")
                    return False
            except (KeyError, ValueError):
                pass
        return True

    def _get_bot_user_id(self):
        if self._bot_user_id is None:
            try:
                me = self.twitter_client.client.get_me(user_auth=True)
                if me and me.data:
                    self._bot_user_id = me.data.id
            except Exception as e:
                logger.warning(f"QuoteTweeter: could not resolve bot user id: {e}")
        return self._bot_user_id

    def _post_quote(self, comment: str, tweet_id: str, author: str) -> str:
        """
        Post a quote tweet, detecting X's engagement-gate rejection.

        X blocks quoting posts from authors who haven't engaged the bot
        (same policy as replies). A rejection marks the author blocked for
        7 days (persisted) so no more Claude calls are wasted on them.

        Returns:
            "ok", "blocked", or "error"
        """
        if not self.twitter_client.should_post:
            logger.info(f"[DEBUG MODE] Would quote-tweet {tweet_id}: {comment[:60]}")
            return "ok"
        try:
            resp = self.twitter_client.client.create_tweet(
                text=comment,
                quote_tweet_id=str(tweet_id),
                user_auth=True
            )
            if resp.data:
                return "ok"
            return "error"
        except Exception as e:
            msg = str(e).lower()
            if "not allowed" in msg or "not been mentioned" in msg or "not part of the conversation" in msg:
                self.state_manager.mark_reply_blocked(author)
                logger.info(f"@{author} quote-blocked by X engagement gate — marked for 7 days")
                return "blocked"
            logger.error(f"QuoteTweeter: error posting quote: {e}")
            return "error"

    # ------------------------------------------------------------------
    # Candidate search
    # ------------------------------------------------------------------

    def _search_candidates(self) -> List[Dict]:
        """One search read; all filtering happens client-side (standard-tier
        search doesn't support engagement operators like min_faves)."""
        try:
            response = self.twitter_client.client.search_recent_tweets(
                query=self.search_query,
                max_results=25,
                tweet_fields=['created_at', 'public_metrics', 'author_id', 'lang'],
                expansions=['author_id'],
                user_fields=['username', 'public_metrics'],
                user_auth=True,
            )
        except Exception as e:
            logger.warning(f"QuoteTweeter: search failed (tier may not include search): {e}")
            return []

        if not response.data:
            logger.debug("QuoteTweeter: search returned no tweets")
            return []

        users = {}
        if response.includes and 'users' in response.includes:
            users = {u.id: u for u in response.includes['users']}

        bot_id = self._get_bot_user_id()
        already_quoted_ids = self.state_manager.quoted_tweet_ids()
        recently_quoted_authors = {
            q.get("author") for q in self.state_manager.quotes_in_last_hours(24)
        }

        candidates = []
        for tweet in response.data:
            author = users.get(tweet.author_id)
            if not author:
                continue
            username = author.username.lower()
            # Skip authors X's engagement gate already rejected (no Claude waste)
            if self.state_manager.is_reply_blocked(username):
                continue
            text = tweet.text or ""
            metrics = tweet.public_metrics or {}
            likes = metrics.get('like_count', 0)
            retweets = metrics.get('retweet_count', 0)
            followers = author.public_metrics.get('followers_count', 0)

            if bot_id and tweet.author_id == bot_id:
                continue
            if str(tweet.id) in already_quoted_ids:
                continue
            if username in recently_quoted_authors:
                continue
            if username in settings.BLOCKED_USERNAMES:
                continue
            if likes < MIN_LIKES or followers < MIN_AUTHOR_FOLLOWERS:
                continue
            if len(text) < MIN_TEXT_LENGTH:
                continue
            lower = text.lower()
            if any(marker in lower for marker in SPAM_MARKERS):
                continue
            if lower.count("$") > 3:  # cashtag-spam shill posts
                continue

            candidates.append({
                'id': str(tweet.id),
                'text': text,
                'author_username': author.username,
                'author_followers': followers,
                'likes': likes,
                'retweets': retweets,
                'score': likes * 2 + retweets * 3 + followers / 200,
            })

        candidates.sort(key=lambda c: c['score'], reverse=True)
        logger.info(f"QuoteTweeter: {len(candidates)} viable candidates from search")
        return candidates

    # ------------------------------------------------------------------
    # Quote a specific tweet (used by the raid engine)
    # ------------------------------------------------------------------

    def quote_specific(self, tweet: Dict) -> bool:
        """
        Quote-tweet a specific tweet (e.g. a monitored account's fresh post).
        Shares the same caps as search-based quoting: daily max, min gap,
        never the same tweet twice, never the same author twice in 24h.
        Skips authors X's engagement gate has rejected (persisted, 7-day retry).

        Args:
            tweet: dict with 'id', 'text', 'author_username' (and optionally
                'likes'/'author_followers' for prompt context)

        Returns:
            True if a quote tweet was posted
        """
        if not self._can_quote_now():
            return False
        if str(tweet['id']) in self.state_manager.quoted_tweet_ids():
            return False
        author = tweet['author_username']
        if self.state_manager.is_reply_blocked(author):
            logger.debug(f"QuoteTweeter: @{author} is engagement-blocked, skipping quote")
            return False
        recently_quoted = {q.get("author") for q in self.state_manager.quotes_in_last_hours(24)}
        if author.lower().lstrip("@") in recently_quoted:
            logger.debug(f"QuoteTweeter: already quoted @{author} in last 24h")
            return False

        prompt = (
            f"You're QUOTE-TWEETING this fresh post from @{author} — an account your "
            f"community follows closely:\n\n"
            f"\"{tweet['text']}\"\n\n"
            f"Write the quote-tweet comment. Rules:\n"
            f"- Under 200 characters, 1-2 lines\n"
            f"- Add a TAKE - agree with a twist, extend the thought, or drop frog wisdom on it. "
            f"Never just restate their point\n"
            f"- Their audience will see this - be the smartest, funniest account in the room\n"
            f"- Tie to pfp/the flywheel/the community ONLY if it fits naturally - forced shilling "
            f"reads desperate\n"
            f"- No @ mentions, no hashtags, no emojis, all lowercase"
        )

        comment = self.generator.generate_tweet(custom_prompt=prompt, use_live_data=False)
        if not comment:
            logger.warning(f"QuoteTweeter: failed to generate comment for @{author}")
            return False

        status = self._post_quote(comment, tweet['id'], author)
        if status != "ok":
            return False

        self.state_manager.record_quote(str(tweet['id']), author)
        logger.info(f"✓ Quote-tweeted @{author} (raid): {comment[:60]}...")
        return True

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run_once(self, max_generation_attempts: int = 2) -> bool:
        """
        One quote-tweet attempt: search, then work down the candidate list.
        If X's engagement gate rejects a candidate's author, that author is
        marked blocked (persisted) and the next candidate is tried — capped
        at max_generation_attempts Claude calls per run so cost stays bounded.

        Returns True if a quote tweet was posted.
        """
        if not self._can_quote_now():
            return False

        candidates = self._search_candidates()
        if not candidates:
            return False

        for best in candidates[:max_generation_attempts]:
            prompt = (
                f"You're QUOTE-TWEETING this post from @{best['author_username']} "
                f"({best['author_followers']:,} followers, {best['likes']} likes):\n\n"
                f"\"{best['text']}\"\n\n"
                f"Write the quote-tweet comment. Rules:\n"
                f"- Under 200 characters, 1-2 lines\n"
                f"- Add a TAKE - agree with a twist, extend the thought, or drop frog wisdom on it. "
                f"Never just restate their point\n"
                f"- Their audience will see this - be the smartest, funniest account in the room\n"
                f"- Tie to pfp/the flywheel/the community ONLY if it fits naturally - forced shilling "
                f"in quote tweets reads desperate\n"
                f"- No @ mentions, no hashtags, no emojis, all lowercase"
            )

            comment = self.generator.generate_tweet(custom_prompt=prompt, use_live_data=False)
            if not comment:
                logger.warning("QuoteTweeter: failed to generate comment")
                return False

            status = self._post_quote(comment, best['id'], best['author_username'])
            if status == "ok":
                self.state_manager.record_quote(best['id'], best['author_username'])
                logger.info(
                    f"✓ Quote-tweeted @{best['author_username']} ({best['likes']} likes): {comment[:60]}..."
                )
                return True
            if status == "blocked":
                continue  # author marked, try next candidate
            return False  # non-policy error — stop this run

        return False
