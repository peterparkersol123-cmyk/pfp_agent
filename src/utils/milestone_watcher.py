"""
On-chain milestone detection for $PFP.

Watches the staking stats and market data the bot already fetches and
detects notable events worth tweeting about in real time:

- Total staked crosses a 25M step (e.g. 575M staked)
- A whale stakes: total staked jumps 5M+ between two checks
- Holder count crosses a 250 step (e.g. 7,500 holders)
- Unique staker count crosses a 25 step
- Price pumps 20%+ in 24h (24h cooldown so it doesn't repeat)

Cost design: detection is pure math on data that's already cached —
a Claude call only happens when a milestone actually fires. Spam guards:
max N milestone tweets per day, minimum gap between them, and baselines
are initialized silently on first run (no "milestone" tweet for a number
that was already crossed before deploy).

State persists to DATA_DIR/milestone_state.json so restarts don't re-fire
old milestones.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.staking_tracker import get_tracker as get_staking_tracker

logger = get_logger(__name__)

# Detection thresholds
STAKED_STEP = 25_000_000      # fire when total staked crosses the next 25M
WHALE_JUMP = 5_000_000        # single-interval staked jump that counts as a whale
HOLDER_STEP = 250             # holder count step
STAKER_STEP = 25              # unique staker count step
PRICE_PUMP_PCT = 20.0         # 24h price change that counts as a pump

# Spam guards
MAX_TWEETS_PER_DAY = 3
MIN_GAP_HOURS = 3
PRICE_PUMP_COOLDOWN_HOURS = 24
# A staked jump only counts as a whale if the two checks are close together
# (a restart after days away must not read slow accumulation as one whale)
WHALE_WINDOW_MINUTES = 90


def _fmt(n: float) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}"


class MilestoneWatcher:
    """Detects on-chain milestones worth tweeting about."""

    def __init__(self, pumpfun_client=None, state_file: Optional[str] = None):
        if state_file is None:
            state_file = str(settings.DATA_DIR / "milestone_state.json")
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()
        # Lazy import avoids pulling the full API client at module load
        if pumpfun_client is None:
            from src.api.pumpfun_client import PumpFunClient
            pumpfun_client = PumpFunClient()
        self.pumpfun_client = pumpfun_client
        logger.info("Initialized MilestoneWatcher")

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load(self) -> Dict:
        try:
            if self.state_file.exists():
                with open(self.state_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading milestone state: {e}")
        return {"fired": {}, "tweet_times": [], "last_staked": None, "last_staked_at": None}

    def _save(self):
        try:
            tmp = self.state_file.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(self.state, f, indent=2)
            os.replace(tmp, self.state_file)
        except Exception as e:
            logger.error(f"Error saving milestone state: {e}")

    # ------------------------------------------------------------------
    # Spam guards
    # ------------------------------------------------------------------

    def _can_tweet_now(self) -> bool:
        now = datetime.now(timezone.utc)
        # Prune tweet timestamps older than 24h
        recent = []
        for ts in self.state.get("tweet_times", []):
            try:
                t = datetime.fromisoformat(ts)
                if now - t < timedelta(hours=24):
                    recent.append(ts)
            except ValueError:
                continue
        self.state["tweet_times"] = recent

        if len(recent) >= MAX_TWEETS_PER_DAY:
            logger.debug("Milestone daily cap reached")
            return False
        if recent:
            last = max(datetime.fromisoformat(ts) for ts in recent)
            if now - last < timedelta(hours=MIN_GAP_HOURS):
                logger.debug("Milestone minimum gap not elapsed")
                return False
        return True

    def record_posted(self):
        """Call after a milestone tweet is successfully posted."""
        self.state.setdefault("tweet_times", []).append(datetime.now(timezone.utc).isoformat())
        self._save()

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def check(self) -> Optional[Dict]:
        """
        Check all milestone conditions against current data.

        Returns the highest-priority event as {"type", "headline", "prompt"},
        or None. Baselines for events NOT returned are left untouched so they
        fire on a later check instead of being silently swallowed.
        """
        stats = get_staking_tracker().get_stats()
        events: List[Dict] = []

        if stats:
            staked = stats.get("totalStaked", 0) or 0
            supply = stats.get("totalSupply", 0) or 0
            stakers = stats.get("uniqueStakers", 0) or 0
            holders = stats.get("totalHolders", 0) or 0
            pct = (staked / supply * 100) if supply else 0

            events.extend(self._check_whale(staked, pct))
            events.extend(self._check_step("staked", staked, STAKED_STEP, lambda v: (
                f"total pfp staked just crossed {_fmt(v)}",
                f"ON-CHAIN MILESTONE (REAL, just happened): total pfp staked just crossed {_fmt(v)} "
                f"({pct:.1f}% of the entire supply now locked, {stakers} stakers). "
                f"Tweet a short hyped reaction. This is the flywheel working - real conviction, "
                f"real numbers. Reference the actual figure."
            )))
            events.extend(self._check_step("holders", holders, HOLDER_STEP, lambda v: (
                f"pfp holder count just crossed {v:,.0f}",
                f"ON-CHAIN MILESTONE (REAL, just happened): pfp holder count just crossed {v:,.0f}. "
                f"The community keeps growing. Tweet a short celebratory reaction - new frens "
                f"joining the army. Reference the actual number."
            )))
            events.extend(self._check_step("stakers", stakers, STAKER_STEP, lambda v: (
                f"unique pfp stakers just crossed {v:,.0f}",
                f"ON-CHAIN MILESTONE (REAL, just happened): {v:,.0f} unique wallets are now staking pfp "
                f"({_fmt(staked)} total staked, {pct:.1f}% of supply). Tweet a short reaction about "
                f"conviction - these are diamond hands locking tokens, not tourists."
            )))

            # Always update whale baseline, even when capped, so the same
            # delta is never counted twice
            self.state["last_staked"] = staked
            self.state["last_staked_at"] = datetime.now(timezone.utc).isoformat()

        events.extend(self._check_price_pump())
        self._save()

        if not events:
            return None
        if not self._can_tweet_now():
            # Event detected but rate-limited — drop it (baselines for step
            # events were already advanced; next step will fire fresh)
            logger.info(f"Milestone detected but rate-limited: {events[0]['headline']}")
            return None

        event = events[0]  # list is built in priority order
        logger.info(f"MILESTONE FIRED: {event['headline']}")
        return event

    def _check_whale(self, staked: float, pct: float) -> List[Dict]:
        """Detect a 5M+ staked jump between two close-together checks."""
        last = self.state.get("last_staked")
        last_at = self.state.get("last_staked_at")
        if last is None or last_at is None:
            return []
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(last_at)
        except ValueError:
            return []
        if age > timedelta(minutes=WHALE_WINDOW_MINUTES):
            return []
        delta = staked - last
        if delta < WHALE_JUMP:
            return []
        return [{
            "type": "whale_stake",
            "headline": f"whale staked {_fmt(delta)} pfp",
            "prompt": (
                f"ON-CHAIN EVENT (REAL, just happened): someone just staked {_fmt(delta)} pfp "
                f"in one move. Total staked is now {_fmt(staked)} ({pct:.1f}% of supply). "
                f"Tweet a short reaction - a whale just locked a serious bag. Don't speculate "
                f"who it is. Pure 'the smart money knows' energy. Reference the actual amount."
            ),
        }]

    def _check_step(self, key: str, value: float, step: float, make_event) -> List[Dict]:
        """
        Fire when `value` crosses the next multiple of `step` upward.
        First sighting sets a silent baseline (no tweet for old news).
        """
        if value <= 0:
            return []
        current_step = int(value // step) * step
        fired = self.state["fired"].get(key)
        if fired is None:
            self.state["fired"][key] = current_step
            return []
        if current_step <= fired:
            return []
        self.state["fired"][key] = current_step
        headline, prompt = make_event(current_step)
        return [{"type": f"{key}_step", "headline": headline, "prompt": prompt}]

    def _check_price_pump(self) -> List[Dict]:
        """Detect a 20%+ 24h pump, with a 24h cooldown."""
        last_pump = self.state.get("last_price_pump_at")
        if last_pump:
            try:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(last_pump)
                if age < timedelta(hours=PRICE_PUMP_COOLDOWN_HOURS):
                    return []
            except ValueError:
                pass

        try:
            pfp = self.pumpfun_client.get_pfp_data()
        except Exception as e:
            logger.warning(f"Milestone watcher: could not fetch price data: {e}")
            return []
        if not pfp:
            return []

        change = pfp.get("price_change_24h", 0)
        if change < PRICE_PUMP_PCT:
            return []

        self.state["last_price_pump_at"] = datetime.now(timezone.utc).isoformat()
        volume = pfp.get("volume_24h", 0)
        return [{
            "type": "price_pump",
            "headline": f"pfp up {change:+.0f}% in 24h",
            "prompt": (
                f"MARKET EVENT (REAL, happening now): pfp is up {change:+.1f}% in the last 24h "
                f"on {_fmt(volume)} volume. Tweet a short reaction - stay cool, you've seen "
                f"pumps before, but let the bullish energy through. Reference the actual move. "
                f"No price predictions."
            ),
        }]
