"""
Test script for the Pump.fun X/Twitter AI Agent.
Tests individual components without posting to Twitter.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Force debug mode for testing
os.environ["DEBUG"] = "True"

from src.utils.logger import setup_logger, get_logger
from src.api.claude_client import ClaudeClient
from src.api.twitter_client import TwitterClient
from src.content.generator import ContentGenerator
from src.content.templates import ContentType
from src.database.operations import DatabaseManager
from src.strategy.topic_manager import TopicManager
from src.strategy.scheduler import PostScheduler

setup_logger()
logger = get_logger(__name__)


def test_claude_api():
    """Test Claude API connection and content generation."""
    logger.info("="*60)
    logger.info("Testing Claude API")
    logger.info("="*60)

    try:
        client = ClaudeClient()

        # Test connection
        if client.test_connection():
            logger.info("✓ Claude API connection successful")
        else:
            logger.error("✗ Claude API connection failed")
            return False

        # Test content generation
        logger.info("Testing content generation...")
        content = client.generate_content(
            prompt="Write a short tweet about Pump.fun in 280 characters or less.",
            max_tokens=100
        )

        if content:
            logger.info(f"✓ Generated content: {content}")
            return True
        else:
            logger.error("✗ Failed to generate content")
            return False

    except Exception as e:
        logger.error(f"✗ Error testing Claude API: {e}")
        return False


def test_twitter_api():
    """Test Twitter API connection."""
    logger.info("="*60)
    logger.info("Testing Twitter API")
    logger.info("="*60)

    try:
        client = TwitterClient()

        # Test connection
        if client.test_connection():
            logger.info("✓ Twitter API connection successful")
            return True
        else:
            logger.error("✗ Twitter API connection failed")
            return False

    except Exception as e:
        logger.error(f"✗ Error testing Twitter API: {e}")
        return False


def test_content_generator():
    """Test content generator."""
    logger.info("="*60)
    logger.info("Testing Content Generator")
    logger.info("="*60)

    try:
        generator = ContentGenerator()

        # Test single tweet generation
        logger.info("Generating single tweet...")
        tweet = generator.generate_tweet(content_type=ContentType.GENERAL)

        if tweet:
            logger.info(f"✓ Generated tweet: {tweet}")
        else:
            logger.error("✗ Failed to generate tweet")
            return False

        # Test thread generation
        logger.info("Generating thread...")
        thread = generator.generate_thread(
            content_type=ContentType.EDUCATIONAL,
            num_tweets=3
        )

        if thread:
            logger.info(f"✓ Generated thread with {len(thread)} tweets:")
            for i, tweet in enumerate(thread, 1):
                logger.info(f"  {i}. {tweet}")
            return True
        else:
            logger.error("✗ Failed to generate thread")
            return False

    except Exception as e:
        logger.error(f"✗ Error testing content generator: {e}")
        return False


def test_database():
    """Test database operations."""
    logger.info("="*60)
    logger.info("Testing Database")
    logger.info("="*60)

    try:
        db = DatabaseManager()

        # Test creating a post
        from src.database.models import Post
        from datetime import datetime

        post = Post(
            content="Test tweet content",
            content_type="general",
            status="pending",
            created_at=datetime.now()
        )

        post_id = db.create_post(post)
        logger.info(f"✓ Created test post with ID: {post_id}")

        # Test retrieving the post
        retrieved_post = db.get_post(post_id)
        if retrieved_post:
            logger.info(f"✓ Retrieved post: {retrieved_post.content}")
        else:
            logger.error("✗ Failed to retrieve post")
            return False

        # Test getting recent posts
        recent_posts = db.get_recent_posts(limit=5)
        logger.info(f"✓ Retrieved {len(recent_posts)} recent posts")

        # Test engagement stats
        stats = db.get_engagement_stats(days=7)
        logger.info(f"✓ Engagement stats: {stats}")

        return True

    except Exception as e:
        logger.error(f"✗ Error testing database: {e}")
        return False


def test_topic_manager():
    """Test topic manager."""
    logger.info("="*60)
    logger.info("Testing Topic Manager")
    logger.info("="*60)

    try:
        topic_manager = TopicManager()

        # Test content type selection
        content_type = topic_manager.select_content_type()
        logger.info(f"✓ Selected content type: {content_type.value}")

        # Test thread decision
        should_thread = topic_manager.should_post_thread()
        logger.info(f"✓ Thread decision: {should_thread}")

        # Test posting time recommendation
        time_rec = topic_manager.get_posting_time_recommendation()
        logger.info(f"✓ Posting time recommendation: {time_rec}")

        return True

    except Exception as e:
        logger.error(f"✗ Error testing topic manager: {e}")
        return False


def test_scheduler():
    """Test scheduler."""
    logger.info("="*60)
    logger.info("Testing Scheduler")
    logger.info("="*60)

    try:
        scheduler = PostScheduler()

        # Test rate limit checking
        can_post, reason = scheduler.can_post_now()
        logger.info(f"✓ Can post now: {can_post}" + (f" ({reason})" if reason else ""))

        # Test status
        status = scheduler.get_status()
        logger.info(f"✓ Scheduler status: {status}")

        return True

    except Exception as e:
        logger.error(f"✗ Error testing scheduler: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("="*60)
    logger.info("Pump.fun X/Twitter AI Agent - Test Suite")
    logger.info("="*60)
    logger.info("")

    tests = [
        ("Database", test_database),
        ("Claude API", test_claude_api),
        ("Twitter API", test_twitter_api),
        ("Content Generator", test_content_generator),
        ("Topic Manager", test_topic_manager),
        ("Scheduler", test_scheduler),
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            logger.info("")
            results[test_name] = test_func()
            logger.info("")
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results[test_name] = False

    # Summary
    logger.info("="*60)
    logger.info("Test Summary")
    logger.info("="*60)

    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        logger.info(f"{test_name:20s} {status}")

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    logger.info("")
    logger.info(f"Results: {passed}/{total} tests passed")

    if passed == total:
        logger.info("✓ All tests passed!")
        return 0
    else:
        logger.error(f"✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
