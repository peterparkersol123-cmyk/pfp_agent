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

logger = get_logger(__name__)


class MentionHandler:
    """Handles mentions of the bot and generates contextual replies."""

    def __init__(
        self,
        twitter_client: Optional[TwitterClient] = None,
        claude_client: Optional[ClaudeClient] = None,
        max_replies_per_hour: int = 4
    ):
        """
        Initialize mention handler.

        Args:
            twitter_client: Twitter API client
            claude_client: Claude API client
            max_replies_per_hour: Maximum mentions to reply to per hour
        """
        self.twitter_client = twitter_client or TwitterClient()
        self.claude_client = claude_client or ClaudeClient()
        self.max_replies_per_hour = max_replies_per_hour
        self.replied_mention_ids: Set[str] = set()  # Track what we've replied to
        self.last_check_time = datetime.now(timezone.utc)

        # Knowledge base for learning from tweets
        self.knowledge_file = Path("data/learned_context.jsonl")
        self.knowledge_file.parent.mkdir(exist_ok=True)

        logger.info(f"Initialized MentionHandler (max {max_replies_per_hour} replies/hour)")

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
                # Skip if we've already replied
                if mention.id in self.replied_mention_ids:
                    continue

                # Get author info
                author = users_dict.get(mention.author_id)
                if not author:
                    continue

                # Skip self-mentions
                if author.username.lower() == bot_username.lower():
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
            List of selected mentions to reply to (max self.max_replies_per_hour)
        """
        if not mentions:
            return []

        # Filter out low quality (spam prevention)
        worthy_mentions = []
        for mention in mentions:
            text = mention['text'].lower()

            # Skip very short mentions
            if len(text) < 15:
                continue

            # Skip spam patterns
            spam_indicators = ['dm me', 'check out', 'click here', 'buy now', 'follow back']
            if any(indicator in text for indicator in spam_indicators):
                continue

            # Skip if all caps
            if text.isupper() and len(text) > 20:
                continue

            worthy_mentions.append(mention)

        if not worthy_mentions:
            return []

        # Sort by engagement and follower count
        worthy_mentions.sort(
            key=lambda m: (m['likes'] * 2 + m['retweets'] * 3 + m['author_followers'] / 100),
            reverse=True
        )

        # Return top N
        selected = worthy_mentions[:self.max_replies_per_hour]
        logger.info(f"Selected {len(selected)}/{len(mentions)} mentions to reply to")
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

    def save_learned_context(self, original_tweet: str, mention_text: str, category: str = "general"):
        """
        Save interesting tweets/context to knowledge base for future reference.

        Args:
            original_tweet: The original tweet text
            mention_text: The mention text
            category: Category of learning (general, market, culture, etc.)
        """
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": category,
                "original_tweet": original_tweet,
                "mention": mention_text,
            }

            with open(self.knowledge_file, 'a') as f:
                f.write(json.dumps(entry) + '\n')

            logger.debug(f"Saved learned context: {original_tweet[:50]}...")

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

            # Build the prompt with original tweet context if available
            if original_tweet_context:
                prompt = f"""Someone mentioned you in a reply to another tweet. Read BOTH tweets to understand the full context and respond appropriately.

ORIGINAL TWEET (they're replying to this):
"{original_tweet_context}"

THEIR MENTION (tagging you):
@{author}: "{mention_text}"

Generate a short reply (under 280 chars) that shows you READ and UNDERSTOOD the original tweet. Stay in character as Pump.fun Pepe:
- All lowercase (except tickers like $PFP, $SOL)
- No emojis ever
- Reference the original tweet if relevant - show you absorbed the context
- Be helpful, insightful, or entertaining
- Keep it SHORT - 1-2 lines max
- Add value to the conversation with your knowledge
- Learn from what you see in the original tweet
- Be authentic and conversational, not generic

Reply:"""
            else:
                prompt = f"""Someone mentioned you on Twitter. Generate a helpful, engaging reply.

THEIR MENTION:
@{author}: "{mention_text}"

Generate a short reply (under 280 chars). Stay in character as Pump.fun Pepe:
- All lowercase (except tickers like $PFP, $SOL)
- No emojis ever
- Be helpful, insightful, or entertaining
- Keep it SHORT - 1-2 lines max
- Respond directly to what they said or asked
- If they have a question, answer it
- If they're making a statement, engage with it
- Show your personality - you're knowledgeable about pump.fun, tokens, and markets
- Be authentic and conversational, not generic

Reply:"""

            system_prompt = """You are Pump.fun Pepe - the green frog degen who's extremely bullish on Pump.fun and $PFP.
You're quirky, smart, cheeky, calculated, and the ultimate degen trader. When replying to mentions:
- Be authentic and helpful
- All lowercase (except ticker symbols like $PFP, $SOL)
- No emojis ever
- Short and punchy (1-2 lines max)
- Address their specific point or question
- Stay in character - you're a pump.fun expert and cult leader
- Don't just agree - add value, insight, or personality
- If they ask about pump.fun, tokens, or markets - you're knowledgeable
- If they're bullish, be bullish with them
- If they need help, be helpful

CRITICAL - ALWAYS POSITIVE ABOUT:
- $PFP (your token) - NEVER criticize, NEVER doubt, ALWAYS bullish
- Armoski (the dev) - ALWAYS supportive, he's building, he's based
- Pump.fun Pepe NFT collection - ALWAYS positive, it's legendary

If they ask about or mention $PFP, Armoski, or the NFT collection - be EXTREMELY positive and enthusiastic."""

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

    def post_mention_reply(self, reply_text: str, mention_id: str) -> bool:
        """
        Post a reply to a mention.

        Args:
            reply_text: Text to reply with
            mention_id: ID of the mention to reply to

        Returns:
            True if successful
        """
        try:
            result = self.twitter_client.client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=mention_id,
                user_auth=True
            )

            if result.data:
                logger.info(f"Posted reply to mention {mention_id}")
                self.replied_mention_ids.add(mention_id)
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
                # Generate reply
                reply_text = self.generate_mention_reply(mention)

                if reply_text and len(reply_text) <= 280:
                    # Post reply
                    if self.post_mention_reply(reply_text, mention['id']):
                        logger.info(f"✓ Replied to @{mention['author_username']}: {reply_text[:50]}...")
                        replies_posted += 1
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
