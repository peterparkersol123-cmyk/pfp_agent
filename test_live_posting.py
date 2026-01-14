#!/usr/bin/env python3
"""
Live posting test - Posts tweets every 1 minute to X.
This uses .env.test configuration for rapid testing.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load test configuration
env_path = Path(__file__).parent / '.env.test'
load_dotenv(env_path, override=True)

from src.utils.logger import setup_logger, get_logger
from src.content.generator import ContentGenerator
from src.api.twitter_client import TwitterClient

setup_logger()
logger = get_logger(__name__)


def main():
    """Run live posting test."""

    # Get posting interval from environment variable
    post_interval_minutes = int(os.getenv('POST_INTERVAL_MINUTES', '30'))
    post_interval_seconds = post_interval_minutes * 60

    print("\n" + "="*70)
    print(f"LIVE POSTING - Every {post_interval_minutes} Minutes")
    print("="*70)
    print()
    print("Configuration:")
    print(f"  Environment: {os.getenv('ENVIRONMENT')}")
    print(f"  Debug Mode: {os.getenv('DEBUG')}")
    print(f"  Post Interval: {post_interval_minutes} minute(s)")
    print()
    print("Starting live posting to X...")
    print("Press Ctrl+C to stop")
    print()

    # Initialize components
    try:
        generator = ContentGenerator()
        twitter = TwitterClient()

        logger.info("Live posting test started")

        tweet_count = 0

        while True:
            try:
                tweet_count += 1
                print(f"\n[Tweet {tweet_count}] Generating...")

                # Generate tweet
                tweet = generator.generate_tweet(use_live_data=True)

                if not tweet:
                    logger.error("Failed to generate tweet")
                    print("  ✗ Failed to generate tweet")
                    time.sleep(post_interval_seconds)
                    continue

                print(f"  Generated: {tweet[:80]}...")
                print(f"  Length: {len(tweet)} chars")

                # Post to Twitter
                print("  Posting to X...")
                result = twitter.post_tweet(tweet)

                if result:
                    tweet_id = result.get('id')
                    print(f"  ✓ Posted successfully!")
                    print(f"  Tweet ID: {tweet_id}")
                    print(f"  URL: https://x.com/i/web/status/{tweet_id}")
                    logger.info(f"Posted tweet {tweet_count}: {tweet[:50]}...")
                else:
                    print("  ✗ Failed to post")
                    logger.error("Failed to post tweet")

                # Wait for configured interval
                print(f"\n  Waiting {post_interval_minutes} minutes until next tweet...")
                print(f"  Next tweet at: {time.strftime('%H:%M:%S', time.localtime(time.time() + post_interval_seconds))}")

                time.sleep(post_interval_seconds)

            except KeyboardInterrupt:
                print("\n\nStopping...")
                break

            except Exception as e:
                logger.error(f"Error in posting loop: {e}", exc_info=True)
                print(f"  ✗ Error: {e}")
                print(f"  Waiting {post_interval_minutes} minutes before retry...")
                time.sleep(post_interval_seconds)

    except KeyboardInterrupt:
        print("\n\nStopped by user")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
        return 1

    print()
    print("="*70)
    print(f"Test completed - Posted {tweet_count} tweets")
    print("="*70)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
