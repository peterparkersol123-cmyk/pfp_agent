"""
Main entry point for the Pump.fun X/Twitter AI Agent.
Orchestrates all components and handles the posting lifecycle.
"""

import sys
import signal
import time
from datetime import datetime
from typing import Optional

from src.config.settings import settings
from src.utils.logger import setup_logger, get_logger
from src.api.claude_client import ClaudeClient
from src.api.twitter_client import TwitterClient
from src.content.generator import ContentGenerator
from src.database.operations import DatabaseManager
from src.database.models import Post
from src.strategy.scheduler import PostScheduler
from src.strategy.topic_manager import TopicManager

# Setup main logger
setup_logger()
logger = get_logger(__name__)


class PumpFunAgent:
    """Main agent orchestrator."""

    def __init__(self):
        """Initialize the agent with all components."""
        logger.info("="*60)
        logger.info("Initializing Pump.fun X/Twitter AI Agent")
        logger.info("="*60)

        # Validate settings
        is_valid, errors = settings.validate()
        if not is_valid:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            raise ValueError("Invalid configuration. Please check your .env file")

        logger.info(f"Environment: {settings.ENVIRONMENT}")
        logger.info(f"Debug mode: {settings.DEBUG}")

        # Initialize components
        try:
            self.db = DatabaseManager()
            self.claude_client = ClaudeClient()
            self.twitter_client = TwitterClient()
            self.content_generator = ContentGenerator(self.claude_client)
            self.topic_manager = TopicManager(self.db)
            self.scheduler = PostScheduler(self.db)

            logger.info("All components initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}", exc_info=True)
            raise

        # Test API connections
        self._test_connections()

        # Track if agent is running
        self.running = False

    def _test_connections(self):
        """Test API connections."""
        logger.info("Testing API connections...")

        # Test Claude API
        if self.claude_client.test_connection():
            logger.info("✓ Claude API connection successful")
        else:
            logger.error("✗ Claude API connection failed")
            raise ConnectionError("Could not connect to Claude API")

        # Test Twitter API
        if settings.should_post_to_twitter():
            if self.twitter_client.test_connection():
                logger.info("✓ Twitter API connection successful")
            else:
                logger.error("✗ Twitter API connection failed")
                raise ConnectionError("Could not connect to Twitter API")
        else:
            logger.info("⚠ Twitter posting disabled (DEBUG mode)")

    def post_content(self):
        """Generate and post content (main posting cycle)."""
        try:
            logger.info("-" * 60)
            logger.info("Starting content generation and posting cycle")

            # Select content type
            content_type = self.topic_manager.select_content_type()
            logger.info(f"Selected content type: {content_type.value}")

            # Decide if thread or single tweet
            is_thread = self.topic_manager.should_post_thread()

            if is_thread:
                logger.info("Creating thread post")
                content = self._post_thread(content_type)
            else:
                logger.info("Creating single tweet")
                content = self._post_single_tweet(content_type)

            if content:
                logger.info("✓ Content posted successfully")
                logger.info("-" * 60)
            else:
                logger.error("✗ Failed to post content")
                logger.info("-" * 60)

        except Exception as e:
            logger.error(f"Error in posting cycle: {e}", exc_info=True)

    def _post_single_tweet(self, content_type) -> Optional[str]:
        """Post a single tweet."""
        # Generate content
        logger.info("Generating tweet content...")
        tweet_content = self.content_generator.generate_tweet(content_type=content_type)

        if not tweet_content:
            logger.error("Failed to generate tweet content")
            return None

        logger.info(f"Generated: {tweet_content}")

        # Check for duplicates
        if self.db.is_duplicate_content(tweet_content, hours=72):
            logger.warning("Content is duplicate - regenerating...")
            tweet_content = self.content_generator.generate_tweet(content_type=content_type)
            if not tweet_content:
                return None

        # Create post record
        post = Post(
            content=tweet_content,
            content_type=content_type.value,
            status="pending",
            created_at=datetime.now(),
            is_thread=False
        )
        post_id = self.db.create_post(post)

        # Post to Twitter
        logger.info("Posting to Twitter...")
        result = self.twitter_client.post_tweet(tweet_content)

        if result:
            # Update post record
            self.db.update_post(
                post_id,
                tweet_id=result["id"],
                status="posted",
                posted_at=datetime.now()
            )

            # Update topic success
            self.topic_manager.update_topic_success(
                topic_name=content_type.value,
                success=True,
                engagement=0  # Will be updated later when we fetch engagement
            )

            logger.info(f"✓ Tweet posted (ID: {result['id']})")
            return tweet_content
        else:
            # Update post record with failure
            self.db.update_post(
                post_id,
                status="failed",
                error_message="Failed to post to Twitter"
            )

            # Update topic success
            self.topic_manager.update_topic_success(
                topic_name=content_type.value,
                success=False
            )

            logger.error("Failed to post tweet to Twitter")
            return None

    def _post_thread(self, content_type) -> Optional[List[str]]:
        """Post a thread of tweets."""
        # Generate thread
        logger.info("Generating thread content...")
        thread_tweets = self.content_generator.generate_thread(
            content_type=content_type,
            num_tweets=3
        )

        if not thread_tweets:
            logger.error("Failed to generate thread content")
            return None

        logger.info(f"Generated thread with {len(thread_tweets)} tweets:")
        for i, tweet in enumerate(thread_tweets, 1):
            logger.info(f"  {i}. {tweet[:100]}...")

        # Create post records for each tweet in thread
        thread_id = f"thread_{int(datetime.now().timestamp())}"
        post_ids = []

        for tweet in thread_tweets:
            post = Post(
                content=tweet,
                content_type=content_type.value,
                status="pending",
                created_at=datetime.now(),
                is_thread=True,
                thread_id=thread_id
            )
            post_ids.append(self.db.create_post(post))

        # Post thread to Twitter
        logger.info("Posting thread to Twitter...")
        results = self.twitter_client.post_thread(thread_tweets)

        if results:
            # Update post records
            for i, (post_id, result) in enumerate(zip(post_ids, results)):
                self.db.update_post(
                    post_id,
                    tweet_id=result["id"],
                    status="posted",
                    posted_at=datetime.now()
                )

            # Update topic success
            self.topic_manager.update_topic_success(
                topic_name=content_type.value,
                success=True,
                engagement=0
            )

            logger.info(f"✓ Thread posted ({len(results)} tweets)")
            return thread_tweets
        else:
            # Update post records with failure
            for post_id in post_ids:
                self.db.update_post(
                    post_id,
                    status="failed",
                    error_message="Failed to post thread to Twitter"
                )

            # Update topic success
            self.topic_manager.update_topic_success(
                topic_name=content_type.value,
                success=False
            )

            logger.error("Failed to post thread to Twitter")
            return None

    def start(self):
        """Start the agent."""
        logger.info("="*60)
        logger.info("Starting Pump.fun X/Twitter AI Agent")
        logger.info("="*60)

        self.running = True

        # Start scheduler
        self.scheduler.start(post_callback=self.post_content)

        # Print status
        status = self.scheduler.get_status()
        logger.info(f"Next post: {status['next_post_in']}")
        logger.info(f"Posts in last hour: {status['posts_last_hour']}/{status['hourly_limit']}")
        logger.info(f"Posts in last day: {status['posts_last_day']}/{status['daily_limit']}")
        logger.info("Agent is now running. Press Ctrl+C to stop.")

        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nReceived interrupt signal")
            self.stop()

    def stop(self):
        """Stop the agent."""
        logger.info("Stopping agent...")
        self.running = False
        self.scheduler.stop()
        logger.info("Agent stopped successfully")

    def get_stats(self):
        """Get and display agent statistics."""
        logger.info("="*60)
        logger.info("Agent Statistics")
        logger.info("="*60)

        # Scheduler status
        scheduler_status = self.scheduler.get_status()
        logger.info("\nScheduler:")
        logger.info(f"  Running: {scheduler_status['running']}")
        logger.info(f"  Next post: {scheduler_status['next_post_in']}")
        logger.info(f"  Posts last hour: {scheduler_status['posts_last_hour']}/{scheduler_status['hourly_limit']}")
        logger.info(f"  Posts last day: {scheduler_status['posts_last_day']}/{scheduler_status['daily_limit']}")

        # Engagement stats
        engagement_stats = self.db.get_engagement_stats(days=7)
        logger.info("\nEngagement (last 7 days):")
        logger.info(f"  Total posts: {engagement_stats['total_posts']}")
        logger.info(f"  Total likes: {engagement_stats['total_likes']}")
        logger.info(f"  Total retweets: {engagement_stats['total_retweets']}")
        logger.info(f"  Total replies: {engagement_stats['total_replies']}")
        logger.info(f"  Avg engagement: {engagement_stats['avg_engagement']:.1f}")

        # Recent posts
        recent_posts = self.db.get_recent_posts(limit=5, status="posted")
        logger.info("\nRecent posts:")
        for post in recent_posts:
            logger.info(f"  [{post.posted_at.strftime('%Y-%m-%d %H:%M')}] {post.content[:60]}...")

        logger.info("="*60)


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"\nReceived signal {signum}")
    sys.exit(0)


def main():
    """Main entry point."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Create and start agent
        agent = PumpFunAgent()

        # Display initial stats
        agent.get_stats()

        # Start the agent
        agent.start()

    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
