"""
Shared rate limiter for Twitter replies across all handlers.
"""

from datetime import datetime, timedelta
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SharedReplyRateLimiter:
    """Tracks and enforces a combined rate limit for all types of replies."""

    def __init__(self, max_replies_per_hour: int = 5):
        """
        Initialize the shared rate limiter.

        Args:
            max_replies_per_hour: Maximum total replies allowed per hour
        """
        self.max_replies_per_hour = max_replies_per_hour
        self.reply_timestamps = []  # List of timestamps when replies were posted
        logger.info(f"Initialized SharedReplyRateLimiter (max {max_replies_per_hour} total replies/hour)")

    def can_reply(self) -> tuple[bool, Optional[str]]:
        """
        Check if a reply can be posted without exceeding rate limit.

        Returns:
            Tuple of (can_reply, reason_if_not)
        """
        # Remove timestamps older than 1 hour
        one_hour_ago = datetime.now() - timedelta(hours=1)
        self.reply_timestamps = [ts for ts in self.reply_timestamps if ts > one_hour_ago]

        # Check if we're at the limit
        if len(self.reply_timestamps) >= self.max_replies_per_hour:
            reason = f"Reply rate limit reached ({len(self.reply_timestamps)}/{self.max_replies_per_hour} in last hour)"
            logger.warning(reason)
            return False, reason

        return True, None

    def record_reply(self):
        """Record that a reply was posted."""
        self.reply_timestamps.append(datetime.now())
        logger.debug(f"Reply recorded. Total in last hour: {len(self.reply_timestamps)}/{self.max_replies_per_hour}")

    def get_remaining_quota(self) -> int:
        """
        Get the number of replies still available in the current hour.

        Returns:
            Number of replies remaining
        """
        # Remove old timestamps
        one_hour_ago = datetime.now() - timedelta(hours=1)
        self.reply_timestamps = [ts for ts in self.reply_timestamps if ts > one_hour_ago]

        return max(0, self.max_replies_per_hour - len(self.reply_timestamps))

    def get_stats(self) -> dict:
        """
        Get current rate limiter statistics.

        Returns:
            Dictionary with stats
        """
        one_hour_ago = datetime.now() - timedelta(hours=1)
        self.reply_timestamps = [ts for ts in self.reply_timestamps if ts > one_hour_ago]

        return {
            "replies_last_hour": len(self.reply_timestamps),
            "max_per_hour": self.max_replies_per_hour,
            "remaining": self.get_remaining_quota()
        }
