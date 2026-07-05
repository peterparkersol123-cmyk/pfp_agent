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
        # conversation_id -> number of replies we've posted in that thread
        self.conversation_turns: Dict[str, int] = state.get("conversation_turns", {})
        # Migrate legacy once-per-thread tracking: any conversation in the old
        # set counts as 1 turn already used
        for cid in self.replied_conversation_ids:
            self.conversation_turns.setdefault(str(cid), 1)
        # Quote tweet history: list of {"at": iso, "tweet_id": str, "author": str}
        self.quote_history: List[Dict] = state.get("quote_history", [])
        # When the last poll was posted (iso str or None)
        self.last_poll_at: Optional[str] = state.get("last_poll_at")

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
                "conversation_turns": self.conversation_turns,
                "quote_history": self.quote_history[-50:],
                "last_poll_at": self.last_poll_at,
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
        """Record that we replied to a mention and count the conversation turn."""
        self.replied_mention_ids.add(mention_id)
        if conversation_id:
            cid = str(conversation_id)
            self.replied_conversation_ids.add(conversation_id)
            self.conversation_turns[cid] = self.conversation_turns.get(cid, 0) + 1
        self._save()

    def get_conversation_turns(self, conversation_id) -> int:
        """How many times we've replied in this conversation thread."""
        return self.conversation_turns.get(str(conversation_id), 0)

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
    # Quote tweets (QuoteTweeter)
    # -------------------------------------------------------------------------

    def record_quote(self, tweet_id: str, author: str):
        """Record a posted quote tweet (for daily caps + dedup)."""
        self.quote_history.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "tweet_id": str(tweet_id),
            "author": author.lower().lstrip("@"),
        })
        self._save()

    def quotes_in_last_hours(self, hours: int = 24) -> List[Dict]:
        """Quote tweets posted within the last N hours."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = []
        for q in self.quote_history:
            try:
                if datetime.fromisoformat(q["at"]) > cutoff:
                    recent.append(q)
            except (KeyError, ValueError):
                continue
        return recent

    def quoted_tweet_ids(self) -> set:
        """All tweet IDs we've ever quoted (dedup)."""
        return {q.get("tweet_id") for q in self.quote_history}

    # -------------------------------------------------------------------------
    # Polls
    # -------------------------------------------------------------------------

    def record_poll(self):
        """Record that a poll was just posted."""
        self.last_poll_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def hours_since_last_poll(self) -> float:
        """Hours since the last poll, or a large number if never."""
        if not self.last_poll_at:
            return 9999.0
        try:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(self.last_poll_at)
            return delta.total_seconds() / 3600
        except ValueError:
            return 9999.0

    # -------------------------------------------------------------------------
    # Recent tweets cache (bot.py main loop)
    # -------------------------------------------------------------------------

    def update_recent_tweets(self, recent_tweets: List[Dict]):
        """Persist the recent tweets cache so the bot resumes tracking on restart."""
        self.recent_tweets = recent_tweets[-10:]
        self._save()
