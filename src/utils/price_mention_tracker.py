"""
Track price action mentions to limit frequency.
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PriceMentionTracker:
    """Tracks when price action was last mentioned to limit frequency."""

    def __init__(self, storage_file: str = "data/price_mentions.json"):
        """
        Initialize the price mention tracker.

        Args:
            storage_file: Path to file for storing mention timestamps
        """
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(exist_ok=True)

        # Load existing data
        self.last_mention_time = self._load_last_mention()
        logger.info(f"Initialized PriceMentionTracker")

    def _load_last_mention(self) -> datetime:
        """Load the last price mention timestamp from file."""
        try:
            if self.storage_file.exists():
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    timestamp_str = data.get('last_mention')
                    if timestamp_str:
                        return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.error(f"Error loading price mention data: {e}")

        # Return a time far in the past if no data
        return datetime.min

    def _save_last_mention(self):
        """Save the last price mention timestamp to file."""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump({
                    'last_mention': self.last_mention_time.isoformat()
                }, f)
        except Exception as e:
            logger.error(f"Error saving price mention data: {e}")

    def can_mention_price(self) -> bool:
        """
        Check if price action can be mentioned based on last mention time.

        Returns:
            True if at least 24 hours have passed since last mention
        """
        time_since_last = datetime.now() - self.last_mention_time
        can_mention = time_since_last >= timedelta(hours=24)

        if can_mention:
            logger.info("Price mention allowed (>24 hours since last mention)")
        else:
            hours_remaining = 24 - (time_since_last.total_seconds() / 3600)
            logger.info(f"Price mention blocked ({hours_remaining:.1f} hours until next allowed)")

        return can_mention

    def record_price_mention(self):
        """Record that a price action mention occurred."""
        self.last_mention_time = datetime.now()
        self._save_last_mention()
        logger.info("Price mention recorded")

    def get_time_until_next_allowed(self) -> float:
        """
        Get hours until next price mention is allowed.

        Returns:
            Hours remaining (0 if already allowed)
        """
        time_since_last = datetime.now() - self.last_mention_time
        hours_passed = time_since_last.total_seconds() / 3600

        if hours_passed >= 24:
            return 0

        return 24 - hours_passed
