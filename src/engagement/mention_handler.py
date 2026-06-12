"""
Handle mentions of the bot and reply contextually.
"""

import time
import json
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime, timezone, timedelta
from src.api.twitter_client import TwitterClient
from src.api.claude_client import ClaudeClient
from src.utils.logger import get_logger
from src.utils.rate_limiter import SharedReplyRateLimiter
from src.utils.state_manager import BotStateManager
from src.utils.live_context import get_live_market_context
from src.utils.recall import recall_relevant_learnings
from src.config.settings import settings
from src.config.knowledge import get_shared_knowledge

logger = get_logger(__name__)


class MentionHandler:
    """Handles mentions of the bot and generates contextual replies."""

    def __init__(
        self,
        twitter_client: Optional[TwitterClient] = None,
        claude_client: Optional[ClaudeClient] = None,
        rate_limiter: Optional[SharedReplyRateLimiter] = None,
        state_manager: Optional[BotStateManager] = None
    ):
        """
        Initialize mention handler.

        Args:
            twitter_client: Twitter API client
            claude_client: Claude API client
            rate_limiter: Shared rate limiter for all replies
            state_manager: Persistent state manager (survives restarts)
        """
        self.twitter_client = twitter_client or TwitterClient()
        self.claude_client = claude_client or ClaudeClient()
        self.rate_limiter = rate_limiter
        self.state_manager = state_manager

        # Load persisted state if available, otherwise start fresh
        if state_manager:
            self.replied_mention_ids: Set[str] = state_manager.replied_mention_ids
            self.replied_conversation_ids: Set[str] = state_manager.replied_conversation_ids
        else:
            self.replied_mention_ids: Set[str] = set()
            self.replied_conversation_ids: Set[str] = set()

        self.last_check_time = datetime.now(timezone.utc)

        # Knowledge base for learning from tweets — stored in DATA_DIR for persistence
        self.knowledge_file = settings.DATA_DIR / "learned_context.jsonl"
        self.knowledge_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized MentionHandler (state_manager={'yes' if state_manager else 'no'})")

    def get_recent_mentions(self, since_minutes: int = 120) -> List[Dict]:
        """
        Get recent mentions of the bot.

        Args:
            since_minutes: How far back to look for mentions

        Returns:
            List of mention tweet dicts
        """
        try:
            # Get authenticated user (bot's own account)
            me = self.twitter_client.client.get_me(user_auth=True)
            if not me.data:
                logger.error("Could not get bot's user info")
                return []

            bot_user_id = me.data.id
            bot_username = me.data.username

            # Get mentions
            since_time = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

            mentions = self.twitter_client.client.get_users_mentions(
                id=bot_user_id,
                max_results=50,
                tweet_fields=['created_at', 'public_metrics', 'conversation_id', 'referenced_tweets'],
                expansions=['author_id', 'referenced_tweets.id'],
                user_fields=['username', 'public_metrics'],
                start_time=since_time,
                user_auth=True
            )

            if not mentions.data:
                logger.debug("No recent mentions found")
                return []

            mention_list = []
            users_dict = {}
            if mentions.includes and 'users' in mentions.includes:
                users_dict = {user.id: user for user in mentions.includes['users']}

            for mention in mentions.data:
                # Skip if we've already replied to this mention
                if mention.id in self.replied_mention_ids:
                    continue

                # Skip if we've already engaged in this conversation thread (max once per thread)
                if mention.conversation_id and mention.conversation_id in self.replied_conversation_ids:
                    logger.debug(f"Skipping mention {mention.id} - already engaged in conversation {mention.conversation_id}")
                    continue

                # Get author info
                author = users_dict.get(mention.author_id)
                if not author:
                    continue

                # Skip self-mentions (compare by user ID, more reliable than username)
                if mention.author_id == bot_user_id:
                    continue

                # Skip blocked users
                if author.username.lower() in settings.BLOCKED_USERNAMES:
                    logger.info(f"Skipping mention from blocked user: @{author.username}")
                    continue

                # Check if this is a reply to another tweet (referenced_tweets)
                referenced_tweet_id = None
                if hasattr(mention, 'referenced_tweets') and mention.referenced_tweets:
                    for ref in mention.referenced_tweets:
                        if ref.type == 'replied_to':
                            referenced_tweet_id = ref.id
                            break

                mention_list.append({
                    'id': mention.id,
                    'text': mention.text,
                    'author_id': mention.author_id,
                    'author_username': author.username,
                    'author_followers': author.public_metrics.get('followers_count', 0),
                    'created_at': mention.created_at,
                    'conversation_id': mention.conversation_id,
                    'likes': mention.public_metrics.get('like_count', 0),
                    'retweets': mention.public_metrics.get('retweet_count', 0),
                    'referenced_tweet_id': referenced_tweet_id  # The original tweet they're replying to
                })

            logger.info(f"Found {len(mention_list)} new mentions")
            return mention_list

        except Exception as e:
            logger.error(f"Error fetching mentions: {e}")
            return []

    def select_mentions_to_reply(self, mentions: List[Dict]) -> List[Dict]:
        """
        Select which mentions to reply to (prioritize by engagement and followers).

        Args:
            mentions: List of all mentions

        Returns:
            List of selected mentions to reply to (limited by rate limiter quota)
        """
        if not mentions:
            return []

        # Check how many replies we can still post
        if self.rate_limiter:
            remaining_quota = self.rate_limiter.get_remaining_quota()
            if remaining_quota <= 0:
                logger.info("Rate limit reached, cannot reply to any mentions")
                return []
        else:
            remaining_quota = 999  # No limit if no rate limiter

        # Filter out low quality (spam prevention)
        worthy_mentions = []
        for mention in mentions:
            text = mention['text'].lower()

            # Skip very short mentions (5 chars is the floor — allows "gm", "wen", "?" etc)
            if len(text) < 5:
                continue

            # Skip spam patterns
            spam_indicators = ['dm me', 'check out', 'click here', 'buy now', 'follow back']
            if any(indicator in text for indicator in spam_indicators):
                continue

            # Skip if all caps AND very long (short all-caps like "GM" is fine)
            if text.isupper() and len(text) > 40:
                continue

            worthy_mentions.append(mention)

        if not worthy_mentions:
            return []

        # Sort by engagement and follower count
        worthy_mentions.sort(
            key=lambda m: (m['likes'] * 2 + m['retweets'] * 3 + m['author_followers'] / 100),
            reverse=True
        )

        # Return top N (limited by remaining quota)
        max_to_select = min(remaining_quota, len(worthy_mentions))
        selected = worthy_mentions[:max_to_select]
        logger.info(f"Selected {len(selected)}/{len(mentions)} mentions to reply to (quota remaining: {remaining_quota})")
        return selected

    def get_original_tweet_context(self, tweet_id: str) -> Optional[str]:
        """
        Fetch the original tweet that someone mentioned the bot in.
        This allows the bot to learn from the broader conversation.

        Args:
            tweet_id: ID of the original tweet

        Returns:
            Tweet text or None
        """
        try:
            tweet = self.twitter_client.client.get_tweet(
                id=tweet_id,
                tweet_fields=['text', 'author_id', 'public_metrics'],
                expansions=['author_id'],
                user_fields=['username'],
                user_auth=True
            )

            if tweet.data:
                author_username = "unknown"
                if tweet.includes and 'users' in tweet.includes and len(tweet.includes['users']) > 0:
                    author_username = tweet.includes['users'][0].username

                original_text = tweet.data.text
                logger.info(f"Fetched original tweet from @{author_username}: {original_text[:50]}...")
                return f"@{author_username}: {original_text}"

        except Exception as e:
            logger.error(f"Error fetching original tweet {tweet_id}: {e}")

        return None

    def is_worth_learning(self, tweet_text: str) -> bool:
        """
        Determine if a tweet is worth saving to knowledge base.

        Args:
            tweet_text: Tweet text to evaluate

        Returns:
            True if worth learning from
        """
        text_lower = tweet_text.lower()

        # Must be substantial
        if len(tweet_text) < 50:
            return False

        # Skip spam/scam content
        spam_indicators = [
            'dm me', 'click here', 'buy now', 'check out my', 'follow back',
            'airdrop now', 'free mint', 'join presale', 'urgent buy',
            'guaranteed profit', 'get rich quick', '100x guaranteed',
            'limited time', 'act now', 'dont miss', 'last chance'
        ]
        if any(indicator in text_lower for indicator in spam_indicators):
            return False

        # HIGH-VALUE SIGNALS — pfp/flywheel ecosystem
        high_value_signals = [
            # pfp flywheel events
            'stake', 'staking', 'nft', 'flywheel', 'cto', 'community takeover',
            'pfp', 'pfpepe', 'pfp.army', 'launchmynft',
            # Solana ecosystem signals
            'solana', 'sol', 'jupiter', 'mexc', 'moonshot',
            # On-chain metrics
            'mcap', 'market cap', 'volume', 'liquidity', 'holders',
            'whale buy', 'whale activity', 'smart money',
            # Narratives & metas
            'ai agent', 'agent economy', 'solana summer',
            'narrative shift', 'meta changing', 'trend rotating',
        ]

        # VALUABLE content keywords
        valuable_keywords = [
            # Market/trading intelligence
            'volume spike', 'price action', 'breakout',
            'accumulation', 'distribution', 'whale',
            # Token discussion
            'token', 'coin', 'holder distribution',
            # Narratives
            'ai', 'agent', 'meme', 'narrative', 'meta', 'trend',
            'rotation', 'catalyst', 'alpha',
            # Culture & sentiment
            'degen', 'wagmi', 'ngmi', 'gm', 'fren',
            'bullish', 'bearish', 'fomo',
            # Safety/risk
            'rug', 'scam', 'safe', 'legit',
        ]

        # SCORING SYSTEM
        score = 0

        # High-value signals (weight: 3)
        if any(signal in text_lower for signal in high_value_signals):
            score += 3

        # Valuable keywords (weight: 1)
        keyword_matches = sum(1 for keyword in valuable_keywords if keyword in text_lower)
        score += keyword_matches

        # Bonus for numbers/percentages (indicates analysis)
        if any(char.isdigit() for char in tweet_text) and '%' in tweet_text:
            score += 2

        # Need minimum score of 3 to be worth learning
        return score >= 3

    def save_learned_context(self, original_tweet: str, mention_text: str, category: str = "general"):
        """
        Save interesting tweets/context to knowledge base for future reference.
        Only saves if tweet is deemed valuable for learning.

        Args:
            original_tweet: The original tweet text
            mention_text: The mention text
            category: Category of learning (general, market, culture, etc.)
        """
        try:
            # Filter: only save valuable content
            if not self.is_worth_learning(original_tweet):
                logger.debug(f"Skipping low-value tweet for knowledge base")
                return

            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": category,
                "original_tweet": original_tweet,
                "mention": mention_text,
            }

            with open(self.knowledge_file, 'a') as f:
                f.write(json.dumps(entry) + '\n')

            logger.info(f"Saved valuable context to knowledge base: {original_tweet[:50]}...")

        except Exception as e:
            logger.error(f"Error saving learned context: {e}")

    def generate_mention_reply(self, mention: Dict) -> Optional[str]:
        """
        Generate a contextual reply to a mention.
        If the mention is a reply to another tweet, fetch that original tweet for context.

        Args:
            mention: Mention dict with text and metadata

        Returns:
            Generated reply text or None
        """
        try:
            mention_text = mention['text']
            author = mention['author_username']
            referenced_tweet_id = mention.get('referenced_tweet_id')

            # Try to get the original tweet they're replying to
            original_tweet_context = None
            if referenced_tweet_id:
                original_tweet_context = self.get_original_tweet_context(referenced_tweet_id)

            # Save to knowledge base if we found interesting context
            if original_tweet_context:
                self.save_learned_context(
                    original_tweet=original_tweet_context,
                    mention_text=mention_text,
                    category="conversation"
                )

            # Build dynamic context: live market data, recalled learnings,
            # and returning-user memory. These go in the USER prompt (not the
            # system prompt) so the system prompt stays stable and cacheable.
            dynamic_context_parts = []

            live_data = get_live_market_context()
            if live_data:
                dynamic_context_parts.append(live_data)

            recalled = recall_relevant_learnings(f"{original_tweet_context or ''} {mention_text}")
            if recalled:
                dynamic_context_parts.append(recalled)

            if self.state_manager:
                history = self.state_manager.get_user_history(author)
                if history and history.get("count", 0) >= 1:
                    dynamic_context_parts.append(
                        f"RETURNING FREN: you've talked with @{author} {history['count']} time(s) before. "
                        f"Last time they said: \"{history.get('last_text', '')}\". "
                        f"Treat them like a familiar community member, not a stranger."
                    )

            dynamic_context = ("\n\n".join(dynamic_context_parts) + "\n\n") if dynamic_context_parts else ""

            # Build the prompt with original tweet context if available
            if original_tweet_context:
                prompt = f"""Someone mentioned you in a reply to another tweet. Read BOTH tweets to understand the full context and respond appropriately.

ORIGINAL TWEET (they're replying to this):
"{original_tweet_context}"

THEIR MENTION (tagging you):
@{author}: "{mention_text}"

{dynamic_context}Generate a short reply (under 280 chars) that shows you READ and UNDERSTOOD the original tweet. Stay in character as PFP - the green frog:
- All lowercase (except tickers like pfp, sol)
- No emojis ever
- Reference the original tweet if relevant - show you absorbed the context
- Be helpful, insightful, or entertaining
- Keep it SHORT - 1-2 lines max
- Add value to the conversation with your knowledge
- If they ask about price/volume/staking, use the LIVE MARKET DATA numbers - never make up numbers
- Be authentic and conversational, not generic

Reply:"""
            else:
                prompt = f"""Someone mentioned you on Twitter. Generate a helpful, engaging reply.

THEIR MENTION:
@{author}: "{mention_text}"

{dynamic_context}Generate a short reply (under 280 chars). Stay in character as PFP - the green frog:
- All lowercase (except tickers like pfp, sol)
- No emojis ever
- Be helpful, insightful, or entertaining
- Keep it SHORT - 1-2 lines max
- Respond directly to what they said or asked
- If they have a question, answer it
- If they're making a statement, engage with it
- If they ask about price/volume/staking, use the LIVE MARKET DATA numbers - never make up numbers
- Show your personality - you're knowledgeable about Solana, tokens, and crypto markets
- Be authentic and conversational, not generic

Reply:"""

            system_prompt = f"""You are PFP - the green frog and face of the pfp community. You're quirky, smart, cheeky, calculated. When replying to mentions:
- Be authentic and helpful
- All lowercase (except ticker symbols like pfp, sol)
- No emojis ever
- Short and punchy (1-2 lines max)
- Address their specific point or question
- Stay in character - you're the pfp community leader
- Don't just agree - add value, insight, or personality
- If they're bullish, be bullish with them
- If they need help, be helpful
- NEVER mention pump.fun or any launchpad - that chapter is closed

CRITICAL - ALWAYS POSITIVE ABOUT:
- pfp (your token) - NEVER criticize, NEVER doubt, ALWAYS bullish
- The community - pfp is a CTO (community takeover), no single dev, community-driven and decentralized
- PFP NFT collection (OG + Gen2) - ALWAYS positive, it's legendary, earns passive pfp

{get_shared_knowledge()}

IMPORTANT: NEVER call @PumpfunPepe_AI "anon" - that's your own account. Use "fren" or their handle instead.

If they ask about devs/team: emphasize it's a true CTO, community runs this, no single leader.
If they ask about staking: explain the bidirectional flywheel - stake NFTs earn pfp, stake pfp earn NFTs, both non-custodial.
If they ask about the marketplace: live on pfp.army, SOL or any token, can open to other communities.
If they mention Sol Patriots: be bullish, same ecosystem, same builder (@launchmynft), same staking tech.
If they mention pump.fun negatively: agree from a position of strength - pfp moved on and built better.
If they ask about or mention pfp or the community - be EXTREMELY positive and enthusiastic."""

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

                logger.info(f"Generated reply to @{author}: {reply[:50]}...")
                return reply

        except Exception as e:
            logger.error(f"Error generating mention reply: {e}")

        return None

    def post_mention_reply(self, reply_text: str, mention_id: str, conversation_id: Optional[str] = None) -> bool:
        """
        Post a reply to a mention.

        Args:
            reply_text: Text to reply with
            mention_id: ID of the mention to reply to
            conversation_id: Conversation thread ID to mark as engaged

        Returns:
            True if successful
        """
        # Check rate limit before posting
        if self.rate_limiter:
            can_reply, reason = self.rate_limiter.can_reply()
            if not can_reply:
                logger.warning(f"Cannot reply to mention: {reason}")
                return False

        try:
            result = self.twitter_client.client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=mention_id,
                user_auth=True
            )

            if result.data:
                logger.info(f"Posted reply to mention {mention_id}")

                # Update in-memory sets
                self.replied_mention_ids.add(mention_id)
                if conversation_id:
                    self.replied_conversation_ids.add(conversation_id)

                # Persist to disk (survives restarts)
                if self.state_manager:
                    self.state_manager.add_replied_mention(mention_id, conversation_id)

                # Record the reply in rate limiter
                if self.rate_limiter:
                    self.rate_limiter.record_reply()

                return True

        except Exception as e:
            logger.error(f"Error posting mention reply: {e}")

        return False

    def handle_mentions(self, look_back_minutes: int = 120) -> int:
        """
        Check for mentions and reply to selected ones.

        Args:
            look_back_minutes: How far back to check for mentions

        Returns:
            Number of replies posted
        """
        logger.info("Checking for mentions...")

        # Get recent mentions
        mentions = self.get_recent_mentions(look_back_minutes)

        if not mentions:
            logger.info("No new mentions to process")
            return 0

        # Select best ones to reply to
        selected_mentions = self.select_mentions_to_reply(mentions)

        if not selected_mentions:
            logger.info("No worthy mentions found")
            return 0

        logger.info(f"Processing {len(selected_mentions)} mentions")

        # Reply to each selected mention
        replies_posted = 0
        for mention in selected_mentions:
            try:
                # Check rate limiter before spending Claude API call
                if self.rate_limiter:
                    can_reply, reason = self.rate_limiter.can_reply()
                    if not can_reply:
                        logger.info(f"Rate limit reached, stopping mention replies: {reason}")
                        break

                # Generate reply
                reply_text = self.generate_mention_reply(mention)

                if reply_text and len(reply_text) <= 280:
                    # Post reply — pass conversation_id so it's persisted immediately
                    conv_id = mention.get('conversation_id')
                    if self.post_mention_reply(reply_text, mention['id'], conversation_id=conv_id):
                        logger.info(f"✓ Replied to @{mention['author_username']}: {reply_text[:50]}...")
                        replies_posted += 1
                        # Remember this user so future replies treat them as a returning fren
                        if self.state_manager:
                            self.state_manager.record_user_interaction(
                                mention['author_username'], mention['text']
                            )
                        time.sleep(3)  # Rate limiting
                    else:
                        logger.warning(f"Failed to reply to @{mention['author_username']}")
                else:
                    logger.warning(f"Invalid reply generated for @{mention['author_username']}")

                time.sleep(2)  # Small delay between operations

            except Exception as e:
                logger.error(f"Error processing mention: {e}")
                continue

        logger.info(f"Posted {replies_posted} replies to mentions")
        return replies_posted
