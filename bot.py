#!/usr/bin/env python3
"""
Production Twitter bot with engagement tracking and reply system.
Posts tweets every N hours and replies to comments.
"""

import os
import sys
import time
import threading
from pathlib import Path
from dotenv import load_dotenv

# Load environment configuration
load_dotenv()

from src.utils.logger import setup_logger, get_logger
from src.content.generator import ContentGenerator
from src.api.twitter_client import TwitterClient
from src.engagement.tracker import EngagementTracker
from src.engagement.reply_handler import ReplyHandler
from src.engagement.account_monitor import AccountMonitor
from src.engagement.mention_handler import MentionHandler
from src.utils.rate_limiter import SharedReplyRateLimiter

setup_logger()
logger = get_logger(__name__)


def mention_monitoring_loop(mention_handler, check_interval_minutes=5, stop_event=None):
    """
    Continuously monitor and reply to mentions in a separate thread.

    Args:
        mention_handler: MentionHandler instance
        check_interval_minutes: How often to check for mentions (default 5 minutes)
        stop_event: Threading event to signal when to stop
    """
    logger.info(f"Started mention monitoring thread (checking every {check_interval_minutes} minutes)")

    while not (stop_event and stop_event.is_set()):
        try:
            logger.debug("Mention monitor: Checking for new mentions...")
            mentions_replied = mention_handler.handle_mentions(look_back_minutes=check_interval_minutes + 2)

            if mentions_replied > 0:
                logger.info(f"Mention monitor: Replied to {mentions_replied} mentions")
            else:
                logger.debug("Mention monitor: No new mentions to reply to")

            # Wait before next check
            for _ in range(check_interval_minutes * 60):
                if stop_event and stop_event.is_set():
                    break
                time.sleep(1)

        except Exception as e:
            logger.error(f"Error in mention monitoring loop: {e}", exc_info=True)
            # Wait a bit before retrying
            time.sleep(60)

    logger.info("Mention monitoring thread stopped")


def main():
    """Run the production bot."""

    # Get configuration from environment
    post_interval_minutes = int(os.getenv('POST_INTERVAL_MINUTES', '300'))
    post_interval_seconds = post_interval_minutes * 60
    enable_replies = os.getenv('ENABLE_REPLY_SYSTEM', 'True').lower() == 'true'
    max_replies_per_tweet = int(os.getenv('MAX_REPLIES_PER_TWEET', '2'))
    max_total_replies_per_hour = int(os.getenv('MAX_TOTAL_REPLIES_PER_HOUR', '5'))
    mention_check_interval = int(os.getenv('MENTION_CHECK_INTERVAL_MINUTES', '5'))

    # Get monitored accounts (comma-separated usernames)
    monitored_accounts_str = os.getenv('MONITORED_ACCOUNTS', '')
    monitored_accounts = [acc.strip().lstrip('@') for acc in monitored_accounts_str.split(',') if acc.strip()]

    print("\n" + "="*70)
    print("PUMP.FUN PEPE BOT - PRODUCTION MODE")
    print("="*70)
    print()
    print("Configuration:")
    print(f"  Environment: {os.getenv('ENVIRONMENT', 'production')}")
    print(f"  Post Interval: {post_interval_minutes} minutes ({post_interval_minutes/60:.1f} hours)")
    print(f"  Reply System: {'Enabled' if enable_replies else 'Disabled'}")
    print(f"  Max Replies Per Tweet: {max_replies_per_tweet}")
    print(f"  Max Total Replies Per Hour: {max_total_replies_per_hour} (combined mentions + comments)")
    print(f"  Mention Monitoring: {'Async (every ' + str(mention_check_interval) + ' min)' if enable_replies else 'Disabled'}")
    print(f"  Monitored Accounts: {len(monitored_accounts)} accounts")
    if monitored_accounts:
        for acc in monitored_accounts:
            print(f"    - @{acc}")
    print()
    print("Starting bot...")
    print("Press Ctrl+C to stop")
    print()

    # Initialize components
    try:
        generator = ContentGenerator()
        twitter = TwitterClient()
        engagement_tracker = EngagementTracker(twitter)

        # Create shared rate limiter for all replies (mentions + tweet comments)
        rate_limiter = SharedReplyRateLimiter(max_replies_per_hour=max_total_replies_per_hour) if enable_replies else None

        reply_handler = ReplyHandler(twitter, max_replies_per_tweet=max_replies_per_tweet, rate_limiter=rate_limiter) if enable_replies else None
        account_monitor = AccountMonitor(twitter, target_usernames=monitored_accounts) if monitored_accounts else None
        mention_handler = MentionHandler(twitter, rate_limiter=rate_limiter) if enable_replies else None

        logger.info("Bot started successfully")

        # Start async mention monitoring thread
        stop_event = threading.Event()
        mention_thread = None
        if mention_handler:
            mention_thread = threading.Thread(
                target=mention_monitoring_loop,
                args=(mention_handler, mention_check_interval, stop_event),
                daemon=True,
                name="MentionMonitor"
            )
            mention_thread.start()
            logger.info("Started async mention monitoring thread")

        tweet_count = 0
        recent_tweets = []  # Store recent tweet IDs for reply checking

        while True:
            try:
                tweet_count += 1
                print(f"\n{'='*70}")
                print(f"[Cycle {tweet_count}] Starting new posting cycle")
                print(f"{'='*70}\n")

                # Step 0: Check monitored accounts and reply to their tweets
                if account_monitor:
                    print("[0/5] Checking monitored accounts for new tweets...")
                    replies_to_accounts = account_monitor.check_and_reply_to_accounts(look_back_minutes=post_interval_minutes + 30)
                    if replies_to_accounts > 0:
                        print(f"  ✓ Posted {replies_to_accounts} replies to monitored accounts")
                    else:
                        print(f"  No new tweets from monitored accounts")
                    print()

                # Note: Mention monitoring now runs asynchronously in separate thread

                # Step 1: Check for replies on recent tweets
                if enable_replies and reply_handler and recent_tweets:
                    print("[1/5] Checking for replies on recent tweets...")
                    for tweet_data in recent_tweets[-3:]:  # Check last 3 tweets
                        tweet_id = tweet_data['id']
                        tweet_text = tweet_data['text']
                        print(f"  Checking tweet {tweet_id}...")

                        # Wait a bit before checking (give people time to reply)
                        age_minutes = (time.time() - tweet_data['timestamp']) / 60
                        if age_minutes < 30:  # Only check tweets older than 30 min
                            print(f"  Tweet too recent ({age_minutes:.0f} min old), skipping")
                            continue

                        replies_posted = reply_handler.handle_tweet_replies(tweet_id, tweet_text)
                        if replies_posted > 0:
                            print(f"  ✓ Posted {replies_posted} replies")
                        else:
                            print(f"  No replies needed")

                        time.sleep(2)  # Rate limiting
                    print()

                # Step 2: Update engagement metrics
                if recent_tweets:
                    print("[2/5] Updating engagement metrics...")
                    for tweet_data in recent_tweets[-5:]:  # Track last 5
                        metrics = engagement_tracker.update_metrics(tweet_data['id'])
                        if metrics:
                            print(f"  Tweet {tweet_data['id'][:10]}... - {metrics['likes']} likes, {metrics['retweets']} RTs")
                        time.sleep(1)

                    # Get top performers
                    top_tweets = engagement_tracker.get_top_performing_tweets(limit=3)
                    if top_tweets:
                        print(f"\n  Top performing tweets:")
                        for i, tweet in enumerate(top_tweets, 1):
                            print(f"    {i}. Score {tweet['score']:.0f}: {tweet['text'][:60]}...")
                    print()

                # Step 3: Generate new tweet (with style learning from top tweets)
                print("[3/5] Generating new tweet...")

                # Check if we have enough data for style learning
                has_style_data = len(engagement_tracker.tracked_tweets) >= 2
                if has_style_data:
                    print("  ℹ Style learning: Active (learning from top tweets)")
                else:
                    print("  ℹ Style learning: Not enough data yet (need 2+ tweets)")

                tweet = generator.generate_tweet(use_live_data=True, engagement_tracker=engagement_tracker)

                if not tweet:
                    logger.error("Failed to generate tweet")
                    print("  ✗ Failed to generate tweet")
                    print(f"\n  Waiting {post_interval_minutes} minutes until next cycle...")
                    time.sleep(post_interval_seconds)
                    continue

                print(f"  Generated: {tweet[:80]}...")
                print(f"  Length: {len(tweet)} chars")

                # Step 4: Post tweet
                print("\n[4/5] Posting to X...")
                result = twitter.post_tweet(tweet)

                if result:
                    tweet_id = result.get('id')
                    print(f"  ✓ Posted successfully!")
                    print(f"  Tweet ID: {tweet_id}")
                    print(f"  URL: https://x.com/i/web/status/{tweet_id}")
                    logger.info(f"Posted tweet {tweet_count}: {tweet[:50]}...")

                    # Track the tweet
                    recent_tweets.append({
                        'id': tweet_id,
                        'text': tweet,
                        'timestamp': time.time()
                    })

                    # Keep only last 10 tweets
                    if len(recent_tweets) > 10:
                        recent_tweets.pop(0)

                    # Start tracking engagement
                    engagement_tracker.track_tweet(tweet_id, tweet)

                else:
                    print("  ✗ Failed to post")
                    logger.error("Failed to post tweet")

                # Wait for next cycle
                next_post_time = time.strftime('%H:%M:%S', time.localtime(time.time() + post_interval_seconds))
                print(f"\n{'='*70}")
                print(f"Cycle {tweet_count} complete")
                print(f"Waiting {post_interval_minutes} minutes ({post_interval_minutes/60:.1f} hours) until next cycle...")
                print(f"Next post at: {next_post_time}")
                print(f"{'='*70}\n")

                time.sleep(post_interval_seconds)

            except KeyboardInterrupt:
                print("\n\nStopping bot...")
                break

            except Exception as e:
                logger.error(f"Error in bot cycle: {e}", exc_info=True)
                print(f"  ✗ Error: {e}")
                print(f"  Waiting {post_interval_minutes} minutes before retry...")
                time.sleep(post_interval_seconds)

    except KeyboardInterrupt:
        print("\n\nStopped by user")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
        return 1

    finally:
        # Stop mention monitoring thread
        if mention_thread and mention_thread.is_alive():
            logger.info("Stopping mention monitoring thread...")
            stop_event.set()
            mention_thread.join(timeout=5)
            logger.info("Mention monitoring thread stopped")

    print()
    print("="*70)
    print(f"Bot stopped - Posted {tweet_count} tweets")
    print("="*70)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
