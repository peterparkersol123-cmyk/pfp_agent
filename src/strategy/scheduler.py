"""
Post scheduler for managing when and how often to post.
"""

import random
from datetime import datetime, timedelta
from typing import Optional, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from src.config.settings import settings
from src.database.operations import DatabaseManager
from src.utils.logger import get_logger
from src.utils.helpers import time_until

logger = get_logger(__name__)


class PostScheduler:
    """Manages posting schedule with rate limiting."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize post scheduler.

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager or DatabaseManager()
        self.scheduler = BackgroundScheduler()

        self.min_interval = settings.MIN_INTERVAL_MINUTES
        self.max_interval = settings.MAX_INTERVAL_MINUTES
        self.base_interval = settings.POST_INTERVAL_MINUTES

        self.max_posts_per_hour = settings.TWITTER_MAX_TWEETS_PER_HOUR
        self.max_posts_per_day = settings.TWITTER_MAX_TWEETS_PER_DAY

        logger.info(f"Initialized PostScheduler (interval: {self.base_interval}min, "
                   f"range: {self.min_interval}-{self.max_interval}min)")

    def start(self, post_callback: Callable):
        """
        Start the scheduler.

        Args:
            post_callback: Function to call when it's time to post
        """
        if self.scheduler.running:
            logger.warning("Scheduler is already running")
            return

        # Calculate next post time
        next_post_time = self._calculate_next_post_time()

        logger.info(f"Starting scheduler - first post in {time_until(next_post_time)}")

        # Add job with interval trigger
        self.scheduler.add_job(
            func=self._post_wrapper,
            trigger=IntervalTrigger(minutes=self.base_interval),
            args=[post_callback],
            id='post_job',
            name='Post Tweet Job',
            replace_existing=True,
            next_run_time=next_post_time
        )

        self.scheduler.start()
        logger.info("Scheduler started successfully")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    def pause(self):
        """Pause the scheduler."""
        if self.scheduler.running:
            self.scheduler.pause()
            logger.info("Scheduler paused")

    def resume(self):
        """Resume the scheduler."""
        if self.scheduler.running:
            self.scheduler.resume()
            logger.info("Scheduler resumed")

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self.scheduler.running

    def can_post_now(self) -> tuple[bool, Optional[str]]:
        """
        Check if posting is allowed based on rate limits.

        Returns:
            Tuple of (can_post, reason_if_not)
        """
        # Check hourly limit
        posts_last_hour = self.db.count_posts_in_timeframe(hours=1)
        if posts_last_hour >= self.max_posts_per_hour:
            reason = f"Hourly limit reached ({posts_last_hour}/{self.max_posts_per_hour})"
            logger.warning(reason)
            return False, reason

        # Check daily limit
        posts_last_day = self.db.count_posts_in_timeframe(hours=24)
        if posts_last_day >= self.max_posts_per_day:
            reason = f"Daily limit reached ({posts_last_day}/{self.max_posts_per_day})"
            logger.warning(reason)
            return False, reason

        return True, None

    def get_next_post_time(self) -> Optional[datetime]:
        """Get the next scheduled post time."""
        job = self.scheduler.get_job('post_job')
        if job:
            return job.next_run_time
        return None

    def reschedule(self, minutes: Optional[int] = None):
        """
        Reschedule the next post.

        Args:
            minutes: Minutes until next post (random if not specified)
        """
        if not self.scheduler.running:
            logger.warning("Cannot reschedule - scheduler not running")
            return

        if minutes is None:
            minutes = self._get_random_interval()

        next_time = datetime.now() + timedelta(minutes=minutes)

        job = self.scheduler.get_job('post_job')
        if job:
            job.modify(next_run_time=next_time)
            logger.info(f"Rescheduled next post to {time_until(next_time)}")

    def _post_wrapper(self, post_callback: Callable):
        """
        Wrapper for post callback with rate limit checking.

        Args:
            post_callback: Function to call for posting
        """
        try:
            # Check if we can post
            can_post, reason = self.can_post_now()

            if not can_post:
                logger.warning(f"Skipping post: {reason}")
                # Reschedule for later
                self.reschedule(minutes=30)
                return

            # Call the posting function
            logger.info("Executing scheduled post")
            post_callback()

            # Reschedule next post with random interval
            self.reschedule()

        except Exception as e:
            logger.error(f"Error in post wrapper: {e}", exc_info=True)
            # Reschedule anyway to keep the cycle going
            self.reschedule(minutes=self.base_interval)

    def _calculate_next_post_time(self, from_time: Optional[datetime] = None) -> datetime:
        """
        Calculate next post time.

        Args:
            from_time: Base time for calculation (defaults to now)

        Returns:
            Next post datetime
        """
        base_time = from_time or datetime.now()
        minutes = self._get_random_interval()
        next_time = base_time + timedelta(minutes=minutes)

        logger.debug(f"Next post calculated: {time_until(next_time)} ({minutes}min)")
        return next_time

    def _get_random_interval(self) -> int:
        """
        Get a random interval within configured bounds.

        Returns:
            Interval in minutes
        """
        # Use base interval +/- 25%
        min_val = max(self.min_interval, int(self.base_interval * 0.75))
        max_val = min(self.max_interval, int(self.base_interval * 1.25))

        return random.randint(min_val, max_val)

    def get_status(self) -> dict:
        """
        Get scheduler status.

        Returns:
            Status dictionary
        """
        next_post = self.get_next_post_time()
        posts_last_hour = self.db.count_posts_in_timeframe(hours=1)
        posts_last_day = self.db.count_posts_in_timeframe(hours=24)

        return {
            "running": self.is_running(),
            "next_post": next_post.isoformat() if next_post else None,
            "next_post_in": time_until(next_post) if next_post else None,
            "posts_last_hour": posts_last_hour,
            "posts_last_day": posts_last_day,
            "hourly_limit": self.max_posts_per_hour,
            "daily_limit": self.max_posts_per_day
        }
