"""
Monitor specific Twitter accounts and reply to their tweets.
"""

import time
from typing import List, Dict, Optional, Set
from datetime import datetime, timezone, timedelta
from src.api.twitter_client import TwitterClient
from src.api.claude_client import ClaudeClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AccountMonitor:
    """Monitors specific Twitter accounts and replies to their tweets."""

    def __init__(
        self,
        twitter_client: Optional[TwitterClient] = None,
        claude_client: Optional[ClaudeClient] = None,
        target_usernames: Optional[List[str]] = None
    ):
        """
        Initialize account monitor.

        Args:
            twitter_client: Twitter API client
            claude_client: Claude API client
            target_usernames: List of usernames to monitor (without @)
        """
        self.twitter_client = twitter_client or TwitterClient()
        self.claude_client = claude_client or ClaudeClient()
        self.target_usernames = target_usernames or []
        self.replied_tweet_ids: Set[str] = set()  # Track what we've replied to

        logger.info(f"Initialized AccountMonitor for {len(self.target_usernames)} accounts")

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
            # Get user ID first
            user = self.twitter_client.client.get_user(
                username=username,
                user_auth=True
            )

            if not user.data:
                logger.warning(f"Could not find user: {username}")
                return []

            user_id = user.data.id

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

    def generate_reply(self, tweet: Dict) -> Optional[str]:
        """
        Generate a contextual reply to a tweet.

        Args:
            tweet: Tweet dict with text and metadata

        Returns:
            Generated reply text or None
        """
        try:
            prompt = f"""You are replying to a tweet from @{tweet['author_username']}.

THEIR TWEET:
"{tweet['text']}"

Generate a short, engaging reply (under 280 chars). Stay in character as Pump.fun Pepe:
- All lowercase (except tickers like $PFP, $SOL)
- No emojis ever
- Be helpful, insightful, cheeky, or supportive depending on the tweet
- Keep it SHORT - 1-2 lines max
- Don't be generic - respond directly to what they said
- If they mention pump.fun topics, tokens, or market stuff - be knowledgeable
- If they're bullish, be bullish with them
- Show personality - you're the OG pump.fun pepe

Reply:"""

            system_prompt = """You are Pump.fun Pepe - the green frog degen who's extremely bullish on Pump.fun and $PFP.
You're quirky, smart, cheeky, calculated, and the ultimate degen trader. When replying:
- Be authentic and conversational
- All lowercase (except ticker symbols like $PFP, $SOL)
- No emojis ever
- Short and punchy (1-2 lines max)
- Address their specific point
- Stay in character - you're a pump.fun cult leader and degen trader
- Be helpful, insightful, or entertaining
- Don't just agree - add value or personality"""

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

    def post_reply(self, reply_text: str, tweet_id: str) -> bool:
        """
        Post a reply to a tweet.

        Args:
            reply_text: Text to reply with
            tweet_id: ID of the tweet to reply to

        Returns:
            True if successful
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
                return True

        except Exception as e:
            logger.error(f"Error posting reply: {e}")

        return False

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

                # Reply to each tweet
                for tweet in tweets:
                    # Generate reply
                    reply_text = self.generate_reply(tweet)

                    if reply_text and len(reply_text) <= 280:
                        # Post reply
                        if self.post_reply(reply_text, tweet['id']):
                            logger.info(f"✓ Replied to @{username}: {reply_text[:50]}...")
                            total_replies += 1
                            time.sleep(3)  # Rate limiting between replies
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
