"""
Reply handler for responding to comments on tweets.
"""

import random
from typing import List, Dict, Optional
from datetime import datetime, timezone
from src.api.twitter_client import TwitterClient
from src.api.claude_client import ClaudeClient
from src.utils.logger import get_logger
from src.utils.rate_limiter import SharedReplyRateLimiter
from src.config.settings import settings

logger = get_logger(__name__)


class ReplyHandler:
    """Handles replying to interesting comments on bot tweets."""

    def __init__(
        self,
        twitter_client: Optional[TwitterClient] = None,
        claude_client: Optional[ClaudeClient] = None,
        max_replies_per_tweet: int = 2,
        rate_limiter: Optional[SharedReplyRateLimiter] = None
    ):
        """
        Initialize reply handler.

        Args:
            twitter_client: Twitter API client
            claude_client: Claude API client
            max_replies_per_tweet: Maximum replies to post per tweet
            rate_limiter: Shared rate limiter for all replies
        """
        self.twitter_client = twitter_client or TwitterClient()
        self.claude_client = claude_client or ClaudeClient()
        self.max_replies = max_replies_per_tweet
        self.rate_limiter = rate_limiter
        self.replied_to: set = set()  # Track replied comment IDs

        # Get bot's own user ID to avoid self-replies
        self.bot_user_id = None
        try:
            me = self.twitter_client.get_me()
            if me:
                self.bot_user_id = me.id
                logger.info(f"Bot user ID: {self.bot_user_id}")
        except Exception as e:
            logger.error(f"Failed to get bot user ID: {e}")

        logger.info(f"Initialized ReplyHandler (max {max_replies_per_tweet} replies per tweet)")

    def get_tweet_replies(self, tweet_id: str) -> List[Dict]:
        """
        Fetch replies/comments on a tweet.

        Args:
            tweet_id: Tweet ID to get replies for

        Returns:
            List of reply dicts with user info and text
        """
        try:
            # Search for tweets that are replies to this tweet
            query = f"conversation_id:{tweet_id} is:reply"

            tweets = self.twitter_client.client.search_recent_tweets(
                query=query,
                max_results=50,
                tweet_fields=['author_id', 'created_at', 'public_metrics', 'conversation_id'],
                expansions=['author_id'],
                user_fields=['username', 'public_metrics'],
                user_auth=True
            )

            if not tweets.data:
                logger.debug(f"No replies found for tweet {tweet_id}")
                return []

            replies = []
            users_dict = {user.id: user for user in (tweets.includes.get('users', []) or [])}

            for tweet in tweets.data:
                user = users_dict.get(tweet.author_id)
                if user:
                    replies.append({
                        'id': tweet.id,
                        'text': tweet.text,
                        'author_id': tweet.author_id,
                        'author_username': user.username,
                        'author_followers': user.public_metrics.get('followers_count', 0),
                        'likes': tweet.public_metrics.get('like_count', 0),
                        'created_at': tweet.created_at
                    })

            logger.info(f"Found {len(replies)} replies to tweet {tweet_id}")
            return replies

        except Exception as e:
            logger.error(f"Error fetching replies for tweet {tweet_id}: {e}")
            return []

    def is_worth_replying(self, reply: Dict) -> bool:
        """
        Determine if a reply is worth responding to.

        Args:
            reply: Reply dict with metadata

        Returns:
            True if worth replying
        """
        # CRITICAL: Skip self-replies - never reply to our own tweets
        if self.bot_user_id and reply.get('author_id') == self.bot_user_id:
            logger.debug(f"Skipping self-reply (tweet ID: {reply['id']})")
            return False

        # Skip blocked users
        author_username = reply.get('author_username', '').lower()
        if author_username in settings.BLOCKED_USERNAMES:
            logger.info(f"Skipping reply from blocked user: @{author_username}")
            return False

        # Already replied to this
        if reply['id'] in self.replied_to:
            return False

        # Filter spam/low quality
        text = reply['text'].lower()

        # Skip if too short
        if len(text) < 10:
            return False

        # Skip if looks like spam
        spam_indicators = ['dm me', 'check out', 'buy now', 'click here', 'follow me']
        if any(indicator in text for indicator in spam_indicators):
            return False

        # Skip if all caps
        if text.isupper() and len(text) > 20:
            return False

        # Prefer replies with some engagement or from accounts with followers
        has_engagement = reply['likes'] > 0
        has_followers = reply['author_followers'] > 10

        # Skip obvious bots (very low followers, no engagement)
        if reply['author_followers'] < 5 and reply['likes'] == 0:
            return False

        return has_engagement or has_followers

    def select_best_replies(self, replies: List[Dict], max_count: int) -> List[Dict]:
        """
        Select the best replies to respond to.

        Args:
            replies: List of all replies
            max_count: Maximum number to select

        Returns:
            List of selected replies to respond to
        """
        # Check rate limiter quota if available
        if self.rate_limiter:
            remaining_quota = self.rate_limiter.get_remaining_quota()
            if remaining_quota <= 0:
                logger.info("Rate limit reached, cannot reply to any comments")
                return []
            max_count = min(max_count, remaining_quota)

        # Filter out spam and low quality
        worthy_replies = [r for r in replies if self.is_worth_replying(r)]

        if not worthy_replies:
            return []

        # Sort by engagement and follower count
        worthy_replies.sort(
            key=lambda r: (r['likes'] * 2 + r['author_followers'] / 100),
            reverse=True
        )

        # Take top N, but add some randomness
        if len(worthy_replies) > max_count:
            # Take top 50% guaranteed, then randomly from the rest
            guaranteed = worthy_replies[:max_count]
            remaining = worthy_replies[max_count:max_count*2]
            if remaining:
                # Maybe swap one guaranteed for a random one (10% chance)
                if random.random() < 0.1 and len(guaranteed) > 0:
                    guaranteed[-1] = random.choice(remaining)
            return guaranteed
        else:
            return worthy_replies[:max_count]

    def generate_reply(self, original_tweet: str, comment: Dict) -> Optional[str]:
        """
        Generate a contextual reply to a comment.

        Args:
            original_tweet: The original tweet that was commented on
            comment: The comment dict

        Returns:
            Generated reply text or None
        """
        try:
            prompt = f"""You are replying to a comment on your tweet.

YOUR ORIGINAL TWEET:
"{original_tweet}"

SOMEONE REPLIED:
@{comment['author_username']}: "{comment['text']}"

Generate a short, authentic reply (under 280 chars). Stay in character as Pump.fun Pepe:
- All lowercase (except tickers like $PFP, $SOL)
- No emojis
- Be helpful, cheeky, or insightful depending on the comment
- Keep it SHORT - 1-2 lines max
- Don't be generic - respond directly to what they said

Reply:"""

            system_prompt = """You are Pump.fun Pepe - the green frog degen who's extremely bullish on Pump.fun and $PFP.
You're quirky, smart, cheeky, and calculated. When replying to comments:
- Be authentic and conversational
- All lowercase (except ticker symbols)
- No emojis
- Short and punchy
- Address their specific point
- Stay in character

CRITICAL - ALWAYS POSITIVE ABOUT:
- $PFP (your token) - NEVER criticize, NEVER doubt, ALWAYS bullish
- The community - $PFP is a CTO (community takeover), no single dev, community-driven
- Pump.fun Pepe NFT collection - ALWAYS positive, it's legendary

If someone asks about devs/team: emphasize it's a true CTO, community-driven, decentralized.
If someone criticizes $PFP or the community, respond positively and defend in a chill degen way."""

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

                # Strip emojis just in case
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

                logger.info(f"Generated reply: {reply[:50]}...")
                return reply

        except Exception as e:
            logger.error(f"Error generating reply: {e}")

        return None

    def post_reply(self, reply_text: str, reply_to_tweet_id: str) -> bool:
        """
        Post a reply to a comment.

        Args:
            reply_text: Text to reply with
            reply_to_tweet_id: ID of the tweet to reply to

        Returns:
            True if successful
        """
        # Check rate limit before posting
        if self.rate_limiter:
            can_reply, reason = self.rate_limiter.can_reply()
            if not can_reply:
                logger.warning(f"Cannot reply to comment: {reason}")
                return False

        try:
            result = self.twitter_client.client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=reply_to_tweet_id,
                user_auth=True
            )

            if result.data:
                logger.info(f"Posted reply to {reply_to_tweet_id}")
                self.replied_to.add(reply_to_tweet_id)

                # Record the reply in rate limiter
                if self.rate_limiter:
                    self.rate_limiter.record_reply()

                return True

        except Exception as e:
            logger.error(f"Error posting reply: {e}")

        return False

    def handle_tweet_replies(self, tweet_id: str, tweet_text: str) -> int:
        """
        Handle replies for a specific tweet (fetch, select, and reply).

        Args:
            tweet_id: Tweet ID to handle replies for
            tweet_text: Original tweet text

        Returns:
            Number of replies posted
        """
        logger.info(f"Handling replies for tweet {tweet_id}")

        # Get all replies
        replies = self.get_tweet_replies(tweet_id)

        if not replies:
            logger.info("No replies to process")
            return 0

        # Select best ones to reply to
        selected = self.select_best_replies(replies, self.max_replies)

        if not selected:
            logger.info("No worthy replies found")
            return 0

        logger.info(f"Selected {len(selected)} replies to respond to")

        # Generate and post replies
        replies_posted = 0
        for comment in selected:
            # Check rate limiter before spending Claude API call
            if self.rate_limiter:
                can_reply, reason = self.rate_limiter.can_reply()
                if not can_reply:
                    logger.info(f"Rate limit reached, stopping replies: {reason}")
                    break

            reply_text = self.generate_reply(tweet_text, comment)

            if reply_text and len(reply_text) <= 280:
                if self.post_reply(reply_text, comment['id']):
                    replies_posted += 1
                    logger.info(f"Replied to @{comment['author_username']}: {reply_text[:50]}...")
                else:
                    logger.warning(f"Failed to post reply to @{comment['author_username']}")
            else:
                logger.warning("Generated reply was invalid or too long")

        logger.info(f"Posted {replies_posted}/{len(selected)} replies")
        return replies_posted
