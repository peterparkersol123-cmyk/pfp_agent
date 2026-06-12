"""
Persist bot interaction state across restarts.

Saves reply tracking sets and recent tweet cache to a JSON file so that
the bot remembers what it has already engaged with after a restart or
Railway redeploy. Uses atomic file writes to avoid corruption.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Set, List, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class BotStateManager:
    """
    Persists all bot state that should survive restarts:
    - Replied mention IDs (MentionHandler)
    - Replied conversation IDs (MentionHandler - max once per thread)
    - Replied comment IDs (ReplyHandler - comments on own tweets)
    - Replied own tweet IDs (ReplyHandler - max once per own tweet)
    - Replied monitored tweet IDs (AccountMonitor)
    - Recent tweets cache (bot.py main loop)
    """

    def __init__(self, state_file: Optional[str] = None):
        """
        Initialize state manager and load persisted state.

        Args:
            state_file: Path to JSON state file. Defaults to data/bot_state.json
                        or DATA_DIR env var if set.

        Environment variables:
            CLEAR_STATE_ON_START=true  — wipe all engagement history on startup.
                                         Use this after switching Twitter accounts so
                                         stale IDs from the old account don't linger.
        """
        if state_file is None:
            data_dir = os.getenv("DATA_DIR", "data")
            state_file = str(Path(data_dir) / "bot_state.json")

        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # CLEAR_STATE_ON_START: wipe persisted state (e.g. after account switch)
        clear_state = os.getenv("CLEAR_STATE_ON_START", "false").lower() == "true"
        if clear_state:
            logger.warning(
                "CLEAR_STATE_ON_START=true — wiping all persisted engagement state. "
                "Remove this env var after the first restart to resume normal tracking."
            )
            state = {}
        else:
            # Load persisted state
            state = self._load()

        self.replied_mention_ids: Set[str] = set(state.get("replied_mention_ids", []))
        self.replied_conversation_ids: Set[str] = set(state.get("replied_conversation_ids", []))
        self.replied_comment_ids: Set[str] = set(state.get("replied_comment_ids", []))
        self.replied_own_tweet_ids: Set[str] = set(state.get("replied_own_tweet_ids", []))
        self.replied_monitored_tweet_ids: Set[str] = set(state.get("replied_monitored_tweet_ids", []))
        self.recent_tweets: List[Dict] = state.get("recent_tweets", [])
        # username (lowercase) -> {"count": int, "last_text": str, "last_at": iso str}
        self.user_interactions: Dict[str, Dict] = state.get("user_interactions", {})

        logger.info(
            f"Loaded bot state from {self.state_file}: "
            f"{len(self.replied_mention_ids)} mention IDs, "
            f"{len(self.replied_conversation_ids)} conversation IDs, "
            f"{len(self.replied_comment_ids)} comment IDs, "
            f"{len(self.replied_own_tweet_ids)} own tweet IDs, "
            f"{len(self.replied_monitored_tweet_ids)} monitored tweet IDs, "
            f"{len(self.recent_tweets)} recent tweets cached"
        )

    def _load(self) -> dict:
        """Load state from JSON file. Returns empty dict on failure."""
        try:
            if self.state_file.exists():
                with open(self.state_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading bot state from {self.state_file}: {e}")
        return {}

    def _save(self):
        """
        Atomically save state to JSON file.
        Writes to a temp file then renames to avoid partial writes on crash.
        """
        try:
            data = {
                "replied_mention_ids": list(self.replied_mention_ids),
                "replied_conversation_ids": list(self.replied_conversation_ids),
                "replied_comment_ids": list(self.replied_comment_ids),
                "replied_own_tweet_ids": list(self.replied_own_tweet_ids),
                "replied_monitored_tweet_ids": list(self.replied_monitored_tweet_ids),
                "recent_tweets": self.recent_tweets[-10:],
                "user_interactions": self.user_interactions,
                "last_saved": datetime.now(timezone.utc).isoformat(),
            }
            tmp_path = self.state_file.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_path, self.state_file)
        except Exception as e:
            logger.error(f"Error saving bot state: {e}")

    # -------------------------------------------------------------------------
    # Mention tracking (MentionHandler)
    # -------------------------------------------------------------------------

    def add_replied_mention(self, mention_id: str, conversation_id: Optional[str] = None):
        """Record that we replied to a mention and optionally its conversation thread."""
        self.replied_mention_ids.add(mention_id)
        if conversation_id:
            self.replied_conversation_ids.add(conversation_id)
        self._save()

    # -------------------------------------------------------------------------
    # Reply tracking (ReplyHandler)
    # -------------------------------------------------------------------------

    def add_replied_comment(self, comment_id: str):
        """Record that we replied to a comment on one of our own tweets."""
        self.replied_comment_ids.add(comment_id)
        self._save()

    def add_replied_own_tweet(self, tweet_id: str):
        """Record that we have engaged with replies on our own tweet (max once)."""
        self.replied_own_tweet_ids.add(tweet_id)
        self._save()

    # -------------------------------------------------------------------------
    # Account monitor tracking (AccountMonitor)
    # -------------------------------------------------------------------------

    def add_replied_monitored_tweet(self, tweet_id: str):
        """Record that we replied to a monitored account's tweet."""
        self.replied_monitored_tweet_ids.add(tweet_id)
        self._save()

    # -------------------------------------------------------------------------
    # Per-user interaction memory (returning frens)
    # -------------------------------------------------------------------------

    def record_user_interaction(self, username: str, text: str):
        """Remember that we interacted with this user and what they said."""
        key = username.lower().lstrip("@")
        entry = self.user_interactions.get(key, {"count": 0})
        entry["count"] = entry.get("count", 0) + 1
        entry["last_text"] = text[:140]
        entry["last_at"] = datetime.now(timezone.utc).isoformat()
        self.user_interactions[key] = entry
        # Cap memory size — keep the 500 most recently seen users
        if len(self.user_interactions) > 500:
            oldest = sorted(self.user_interactions.items(), key=lambda kv: kv[1].get("last_at", ""))
            for k, _ in oldest[: len(self.user_interactions) - 500]:
                del self.user_interactions[k]
        self._save()

    def get_user_history(self, username: str) -> Optional[Dict]:
        """Return interaction history for a user, or None if first contact."""
        return self.user_interactions.get(username.lower().lstrip("@"))

    # -------------------------------------------------------------------------
    # Recent tweets cache (bot.py main loop)
    # -------------------------------------------------------------------------

    def update_recent_tweets(self, recent_tweets: List[Dict]):
        """Persist the recent tweets cache so the bot resumes tracking on restart."""
        self.recent_tweets = recent_tweets[-10:]
        self._save()
