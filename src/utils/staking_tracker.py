"""
Live staking stats tracker for $PFP.

Fetches from https://staking.pfpepe.fun/api/staking/stats every 30 minutes
and caches the result so all bot components can reference the live staked amount
without hammering the API.
"""

import threading
import time
import requests
from typing import Optional, Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)

_STATS_URL = "https://staking.pfpepe.fun/api/staking/stats"
_REFRESH_INTERVAL = 30 * 60  # 30 minutes

# Module-level singleton so all bot components share one tracker/thread
_tracker_instance: Optional["StakingTracker"] = None
_tracker_lock = threading.Lock()


def get_tracker() -> "StakingTracker":
    """Return the shared StakingTracker singleton (creates it on first call)."""
    global _tracker_instance
    if _tracker_instance is None:
        with _tracker_lock:
            if _tracker_instance is None:
                _tracker_instance = StakingTracker()
    return _tracker_instance


def _fmt(n: float) -> str:
    """Format a large number as a human-readable string (e.g. 366.35M)."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}"


class StakingTracker:
    """
    Background thread that refreshes $PFP coin-staking stats every 30 minutes.

    Usage:
        tracker = StakingTracker()
        context = tracker.get_context_string()   # inject into prompts
        label   = tracker.get_staked_label()     # e.g. "366.35M"
    """

    def __init__(self):
        self._stats: Optional[Dict] = None
        self._lock = threading.Lock()

        # Fetch immediately so stats are ready before the first tweet
        self._fetch()

        # Keep refreshing in the background
        t = threading.Thread(target=self._refresh_loop, daemon=True, name="StakingTracker")
        t.start()
        logger.info("StakingTracker started")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch(self):
        """Fetch stats from the API and update cache."""
        try:
            resp = requests.get(_STATS_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            with self._lock:
                self._stats = data
            staked = data.get("totalStaked", 0)
            stakers = data.get("uniqueStakers", 0)
            logger.info(
                f"Staking stats refreshed: {_fmt(staked)} $PFP staked, "
                f"{stakers} unique stakers"
            )
        except Exception as e:
            logger.warning(f"StakingTracker: failed to fetch stats: {e}")

    def _refresh_loop(self):
        while True:
            time.sleep(_REFRESH_INTERVAL)
            self._fetch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_stats(self) -> Optional[Dict]:
        """Return raw stats dict or None if not yet fetched."""
        with self._lock:
            return dict(self._stats) if self._stats else None

    def get_staked_label(self) -> str:
        """
        Returns the staked amount as a human-readable label.
        Falls back to '220M+' if stats are unavailable.
        """
        stats = self.get_stats()
        if not stats:
            return "220M+"
        return _fmt(stats.get("totalStaked", 0))

    def get_context_string(self) -> Optional[str]:
        """
        Returns a one-line context string suitable for injecting into prompts.
        Returns None if stats are unavailable.
        """
        stats = self.get_stats()
        if not stats:
            return None

        total_staked = stats.get("totalStaked", 0)
        total_supply = stats.get("totalSupply", 0)
        unique_stakers = stats.get("uniqueStakers", 0)
        staked_pct = (total_staked / total_supply * 100) if total_supply > 0 else 0

        return (
            f"- $PFP COIN STAKING (LIVE): {_fmt(total_staked)} tokens staked "
            f"({staked_pct:.1f}% of supply locked), {unique_stakers} unique stakers"
        )
