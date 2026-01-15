#!/usr/bin/env python3
"""
Production Twitter bot with engagement tracking and reply system.
Posts tweets every N hours and replies to comments.
"""

import os
import sys
import time
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

setup_logger()
logger = get_logger(__name__)


def main():
    """Run the production bot."""

    # Get configuration from environment
    post_interval_minutes = int(os.getenv('POST_INTERVAL_MINUTES', '300'))
    post_interval_seconds = post_interval_minutes * 60
    enable_replies = os.getenv('ENABLE_REPLY_SYSTEM', 'True').lower() == 'true'
    max_replies_per_tweet = int(os.getenv('MAX_REPLIES_PER_TWEET', '2'))

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
        reply_handler = ReplyHandler(twitter, max_replies_per_tweet=max_replies_per_tweet) if enable_replies else None
        account_monitor = AccountMonitor(twitter, target_usernames=monitored_accounts) if monitored_accounts else None
        mention_handler = MentionHandler(twitter, max_replies_per_hour=4) if enable_replies else None

        logger.info("Bot started successfully")

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
                    print("[0/6] Checking monitored accounts for new tweets...")
                    replies_to_accounts = account_monitor.check_and_reply_to_accounts(look_back_minutes=post_interval_minutes + 30)
                    if replies_to_accounts > 0:
                        print(f"  ✓ Posted {replies_to_accounts} replies to monitored accounts")
                    else:
                        print(f"  No new tweets from monitored accounts")
                    print()

                # Step 0.5: Check for mentions and reply
                if mention_handler:
                    print("[0.5/6] Checking for mentions...")
                    mentions_replied = mention_handler.handle_mentions(look_back_minutes=post_interval_minutes + 30)
                    if mentions_replied > 0:
                        print(f"  ✓ Replied to {mentions_replied} mentions")
                    else:
                        print(f"  No new mentions to reply to")
                    print()

                # Step 1: Check for replies on recent tweets
                if enable_replies and reply_handler and recent_tweets:
                    print("[1/6] Checking for replies on recent tweets...")
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
                    print("[2/6] Updating engagement metrics...")
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
                print("[3/6] Generating new tweet...")

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
                print("\n[4/6] Posting to X...")
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

    print()
    print("="*70)
    print(f"Bot stopped - Posted {tweet_count} tweets")
    print("="*70)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
