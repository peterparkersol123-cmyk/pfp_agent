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
from src.utils.state_manager import BotStateManager

setup_logger()
logger = get_logger(__name__)


def mention_monitoring_loop(mention_handler, check_interval_minutes=5, stop_event=None,
                            state_manager=None, slow_interval_minutes=20):
    """
    Continuously monitor and reply to mentions in a separate thread.

    Polls adaptively: fast (check_interval_minutes) for the first 2 hours after
    our latest post — when mentions actually arrive — and slow
    (slow_interval_minutes) the rest of the time to save X API read quota.

    Args:
        mention_handler: MentionHandler instance
        check_interval_minutes: Fast polling interval (default 5 minutes)
        stop_event: Threading event to signal when to stop
        state_manager: BotStateManager, used to know when we last posted
        slow_interval_minutes: Polling interval when no recent post (default 20)
    """
    logger.info(
        f"Started mention monitoring thread "
        f"(every {check_interval_minutes} min for 2h after a post, every {slow_interval_minutes} min otherwise)"
    )

    while not (stop_event and stop_event.is_set()):
        try:
            # Fast polling only pays off while a fresh post is drawing mentions
            interval = slow_interval_minutes
            if state_manager and state_manager.recent_tweets:
                last_post_ts = state_manager.recent_tweets[-1].get('timestamp', 0)
                minutes_since_post = (time.time() - last_post_ts) / 60
                if minutes_since_post < 120:
                    interval = check_interval_minutes

            logger.debug("Mention monitor: Checking for new mentions...")
            # Use at least 120 min look-back so mentions aren't missed after restarts.
            # replied_mention_ids prevents double-replies.
            look_back = max(interval * 2 + 5, 120)
            mentions_replied = mention_handler.handle_mentions(look_back_minutes=look_back)

            if mentions_replied > 0:
                logger.info(f"Mention monitor: Replied to {mentions_replied} mentions")
            else:
                logger.debug("Mention monitor: No new mentions to reply to")

            # Wait before next check
            for _ in range(interval * 60):
                if stop_event and stop_event.is_set():
                    break
                time.sleep(1)

        except Exception as e:
            logger.error(f"Error in mention monitoring loop: {e}", exc_info=True)
            # Wait a bit before retrying
            time.sleep(60)

    logger.info("Mention monitoring thread stopped")


def milestone_monitoring_loop(watcher, generator, twitter, engagement_tracker,
                              check_interval_minutes=20, stop_event=None):
    """
    Watch on-chain stats and tweet when a real milestone fires
    (staking thresholds, whale stakes, holder growth, price pumps).

    Detection is free (cached data) — Claude is only called when a
    milestone actually fires, and the watcher caps milestone tweets
    at 3/day with a 3h minimum gap.
    """
    logger.info(f"Started milestone monitoring thread (checking every {check_interval_minutes} minutes)")

    while not (stop_event and stop_event.is_set()):
        try:
            event = watcher.check()
            if event:
                logger.info(f"Milestone event: {event['headline']} — generating tweet")
                tweet = generator.generate_tweet(custom_prompt=event["prompt"], use_live_data=False)
                if tweet:
                    result = twitter.post_tweet(tweet)
                    if result:
                        tweet_id = result.get("id")
                        watcher.record_posted()
                        engagement_tracker.track_tweet(tweet_id, tweet, content_type="milestone")
                        logger.info(f"✓ Posted milestone tweet ({event['type']}): {tweet[:60]}...")
                        print(f"\n  ⚡ MILESTONE TWEET POSTED ({event['headline']}): {tweet[:80]}")
                    else:
                        logger.error("Failed to post milestone tweet")
                else:
                    logger.warning("Failed to generate milestone tweet")

            # Wait before next check
            for _ in range(check_interval_minutes * 60):
                if stop_event and stop_event.is_set():
                    break
                time.sleep(1)

        except Exception as e:
            logger.error(f"Error in milestone monitoring loop: {e}", exc_info=True)
            time.sleep(60)

    logger.info("Milestone monitoring thread stopped")


def main():
    """Run the production bot."""

    # Get configuration from environment
    post_interval_minutes = int(os.getenv('POST_INTERVAL_MINUTES', '1440'))
    post_interval_seconds = post_interval_minutes * 60
    enable_replies = os.getenv('ENABLE_REPLY_SYSTEM', 'True').lower() == 'true'
    max_replies_per_tweet = int(os.getenv('MAX_REPLIES_PER_TWEET', '3'))
    max_total_replies_per_hour = int(os.getenv('MAX_TOTAL_REPLIES_PER_HOUR', '20'))
    mention_check_interval = int(os.getenv('MENTION_CHECK_INTERVAL_MINUTES', '5'))
    mention_check_slow_interval = int(os.getenv('MENTION_CHECK_INTERVAL_SLOW_MINUTES', '20'))
    enable_milestones = os.getenv('ENABLE_MILESTONE_TWEETS', 'True').lower() == 'true'
    milestone_check_interval = int(os.getenv('MILESTONE_CHECK_INTERVAL_MINUTES', '20'))

    # Get monitored accounts (comma-separated usernames)
    monitored_accounts_str = os.getenv('MONITORED_ACCOUNTS', '')
    monitored_accounts = [acc.strip().lstrip('@') for acc in monitored_accounts_str.split(',') if acc.strip()]

    print("\n" + "="*70)
    print("PFP BOT (@PumpfunPepe_AI) - PRODUCTION MODE")
    print("="*70)
    print()
    print("Configuration:")
    print(f"  Environment: {os.getenv('ENVIRONMENT', 'production')}")
    print(f"  Post Interval: {post_interval_minutes} minutes ({post_interval_minutes/60:.1f} hours)")
    print(f"  Reply System: {'Enabled' if enable_replies else 'Disabled'}")
    print(f"  Max Replies Per Tweet: {max_replies_per_tweet}")
    print(f"  Max Total Replies Per Hour: {max_total_replies_per_hour} (combined mentions + comments)")
    print(f"  Mention Monitoring: {'Async (every ' + str(mention_check_interval) + ' min for 2h after a post, else every ' + str(mention_check_slow_interval) + ' min)' if enable_replies else 'Disabled'}")
    print(f"  Milestone Tweets: {'Enabled (every ' + str(milestone_check_interval) + ' min, max 3/day)' if enable_milestones else 'Disabled'}")
    print(f"  Monitored Accounts: {len(monitored_accounts)} accounts")
    if monitored_accounts:
        for acc in monitored_accounts:
            print(f"    - @{acc}")
    print()
    print("Starting bot...")
    print("Press Ctrl+C to stop")
    print()

    # Defined before the try so the finally block can reference them safely
    # even if component initialization fails
    stop_event = threading.Event()
    mention_thread = None
    milestone_thread = None

    # Initialize components
    try:
        generator = ContentGenerator()
        twitter = TwitterClient()
        engagement_tracker = EngagementTracker(twitter)

        # Create persistent state manager — loads all prior engagement history from disk
        state_manager = BotStateManager()
        logger.info("Bot state loaded from disk")

        # Create shared rate limiter for all replies (mentions + tweet comments)
        rate_limiter = SharedReplyRateLimiter(max_replies_per_hour=max_total_replies_per_hour) if enable_replies else None

        reply_handler = ReplyHandler(twitter, max_replies_per_tweet=max_replies_per_tweet, rate_limiter=rate_limiter, state_manager=state_manager) if enable_replies else None
        account_monitor = AccountMonitor(twitter, target_usernames=monitored_accounts, rate_limiter=rate_limiter, state_manager=state_manager) if monitored_accounts else None
        mention_handler = MentionHandler(twitter, rate_limiter=rate_limiter, state_manager=state_manager) if enable_replies else None

        # Confirm which Twitter account we're authenticated as
        try:
            me = twitter.client.get_me(user_auth=True)
            if me and me.data:
                logger.info(f"Authenticated as @{me.data.username} (ID: {me.data.id})")
                print(f"  Authenticated as: @{me.data.username}")
            else:
                logger.warning("Could not confirm authenticated Twitter account")
        except Exception as e:
            logger.warning(f"Could not verify Twitter account identity: {e}")

        logger.info("Bot started successfully")

        # Start async mention monitoring thread
        if mention_handler:
            mention_thread = threading.Thread(
                target=mention_monitoring_loop,
                args=(mention_handler, mention_check_interval, stop_event,
                      state_manager, mention_check_slow_interval),
                daemon=True,
                name="MentionMonitor"
            )
            mention_thread.start()
            logger.info("Started async mention monitoring thread")

        # Start async milestone monitoring thread (on-chain event tweets)
        if enable_milestones:
            from src.utils.milestone_watcher import MilestoneWatcher
            milestone_watcher = MilestoneWatcher()
            milestone_thread = threading.Thread(
                target=milestone_monitoring_loop,
                args=(milestone_watcher, generator, twitter, engagement_tracker,
                      milestone_check_interval, stop_event),
                daemon=True,
                name="MilestoneMonitor"
            )
            milestone_thread.start()
            logger.info("Started async milestone monitoring thread")

        tweet_count = 0
        # Restore recent tweets from persisted state so reply checking resumes after restart
        recent_tweets = state_manager.recent_tweets[:]
        if recent_tweets:
            logger.info(f"Restored {len(recent_tweets)} recent tweets from persisted state")

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
                    # One batch read for every tracked tweet (up to 100) instead
                    # of one API call per tweet — better learning data, fewer reads
                    engagement_tracker.update_metrics_batch(list(engagement_tracker.tracked_tweets.keys()))
                    for tweet_data in recent_tweets[-5:]:
                        metrics = engagement_tracker.tracked_tweets.get(tweet_data['id'])
                        if metrics:
                            print(f"  Tweet {tweet_data['id'][:10]}... - {metrics['likes']} likes, {metrics['retweets']} RTs")

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

                    # Persist recent tweets so the bot resumes tracking on restart
                    state_manager.update_recent_tweets(recent_tweets)

                    # Start tracking engagement (tagged with content type for topic learning)
                    engagement_tracker.track_tweet(tweet_id, tweet, content_type=generator.last_content_type)

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
        # Stop background monitoring threads
        stop_event.set()
        if mention_thread and mention_thread.is_alive():
            logger.info("Stopping mention monitoring thread...")
            mention_thread.join(timeout=5)
            logger.info("Mention monitoring thread stopped")
        if milestone_thread and milestone_thread.is_alive():
            logger.info("Stopping milestone monitoring thread...")
            milestone_thread.join(timeout=5)
            logger.info("Milestone monitoring thread stopped")

    print()
    print("="*70)
    print(f"Bot stopped - Posted {tweet_count} tweets")
    print("="*70)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
