"""
Persistent intelligence engine — the bot's evolving "brain".

The old learning loop re-derived insights from the last 30 raw tweets every
4 hours and threw them away. This engine instead maintains a *persistent,
structured brief* that accumulates over time: it feeds new tweets the bot
has interacted with into its current understanding and asks Claude to MERGE
them in — updating momentum, letting stale narratives decay, and keeping a
running read on community mood, live narratives, current slang, and alpha.

That brief is injected into future tweets and replies, so the bot's voice
tracks what CT actually cares about right now instead of guessing.

Cost design:
- Updates run at most once per UPDATE_COOLDOWN_HOURS (default 6) and only
  when enough new material has accumulated — ~4 cheap (Haiku) calls/day max.
- Only NEW knowledge-file entries since the last update are processed.
- The brief is bounded in size, so prompt-injection cost stays small and
  the system prompt around it stays cacheable.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

import threading

UPDATE_COOLDOWN_HOURS = 6
MIN_NEW_ENTRIES = 5
NARRATIVE_STALE_DAYS = 5          # drop narratives not seen in this long
MAX_NARRATIVES = 8
MAX_ALPHA = 6
MAX_VOCAB = 15


class IntelligenceEngine:
    """Maintains and evolves the bot's distilled market/community intelligence."""

    def __init__(self, claude_client=None):
        self.claude_client = claude_client  # may be set later
        self.knowledge_file = settings.DATA_DIR / "learned_context.jsonl"
        self.brief_file = settings.DATA_DIR / "intelligence.json"
        self.brief_file.parent.mkdir(parents=True, exist_ok=True)
        self.brief = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> Dict:
        try:
            if self.brief_file.exists():
                with open(self.brief_file) as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Intelligence: could not load brief: {e}")
        return {
            "updated_at": None,
            "processed_lines": 0,      # how many knowledge-file lines folded in
            "community_mood": "",
            "narratives": [],          # {topic, sentiment, momentum, note, last_seen}
            "alpha": [],               # durable facts/events worth remembering
            "vocabulary": [],          # slang/memes currently in use
            "watch": [],               # things to keep an eye on
        }

    def _save(self):
        try:
            tmp = self.brief_file.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(self.brief, f, indent=2)
            tmp.replace(self.brief_file)
        except Exception as e:
            logger.error(f"Intelligence: could not save brief: {e}")

    # ------------------------------------------------------------------
    # Reading new source material
    # ------------------------------------------------------------------

    def _new_entries(self) -> List[Dict]:
        """Knowledge-file entries added since the last update."""
        if not self.knowledge_file.exists():
            return []
        try:
            with open(self.knowledge_file) as f:
                lines = f.readlines()
        except Exception:
            return []

        start = self.brief.get("processed_lines", 0)
        # File may have been trimmed/rotated — reset if it shrank
        if start > len(lines):
            start = 0
        new = []
        for line in lines[start:]:
            try:
                new.append(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
        self._pending_line_count = len(lines)
        return new

    # ------------------------------------------------------------------
    # Update (the actual learning step)
    # ------------------------------------------------------------------

    def _due_for_update(self) -> bool:
        updated_at = self.brief.get("updated_at")
        if not updated_at:
            return True
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(updated_at)
            return age >= timedelta(hours=UPDATE_COOLDOWN_HOURS)
        except ValueError:
            return True

    def update(self, force: bool = False) -> bool:
        """
        Fold new interacted tweets into the persistent brief. Cheap and rate
        limited — returns True only if the brief was actually refreshed.
        """
        if self.claude_client is None:
            return False
        if not force and not self._due_for_update():
            return False

        new_entries = self._new_entries()
        if not force and len(new_entries) < MIN_NEW_ENTRIES:
            logger.debug(f"Intelligence: only {len(new_entries)} new entries, waiting for {MIN_NEW_ENTRIES}")
            return False
        if not new_entries:
            return False

        # Format the new material compactly
        lines = []
        for e in new_entries[-40:]:  # cap what we feed per update
            src = e.get("source", "")
            txt = (e.get("original_tweet") or e.get("mention") or "").strip().replace("\n", " ")
            if len(txt) > 10:
                lines.append(f"- {src}: {txt[:200]}" if src else f"- {txt[:200]}")
        if not lines:
            return False
        new_material = "\n".join(lines)

        current_brief = json.dumps({
            k: self.brief[k] for k in ("community_mood", "narratives", "alpha", "vocabulary", "watch")
        }, indent=2)

        prompt = f"""You are the memory of PFP, a Solana memecoin community bot. You maintain a running intelligence brief about crypto Twitter, the Solana memecoin scene, and the pfp/Sol Patriots community.

YOUR CURRENT BRIEF:
{current_brief}

NEW TWEETS the bot just interacted with (accounts it watches + people who talked to it):
{new_material}

Produce an UPDATED brief as JSON. Rules:
- MERGE the new info into what you already know — don't start from scratch
- Update each narrative's momentum: "rising", "steady", or "fading". If a narrative in the current brief isn't reinforced by new tweets, mark it fading or drop it
- Keep it real and specific — actual narratives/alpha/slang, not generic filler
- "vocabulary" = current slang, memes, and phrases CT is using right now, so the bot talks current
- "alpha" = durable facts or events worth remembering (launches, partnerships, notable moves)
- Be concise. Max {MAX_NARRATIVES} narratives, {MAX_ALPHA} alpha, {MAX_VOCAB} vocabulary items

Respond with ONLY this JSON, nothing else:
{{
  "community_mood": "one short sentence on overall sentiment right now",
  "narratives": [{{"topic": "...", "sentiment": "bullish|bearish|neutral", "momentum": "rising|steady|fading", "note": "one short line"}}],
  "alpha": ["..."],
  "vocabulary": ["..."],
  "watch": ["things worth watching next"]
}}"""

        try:
            response = self.claude_client.generate_content(
                prompt=prompt,
                system_prompt="You distill crypto Twitter intelligence into a tight JSON brief. Accurate, specific, concise. Output only valid JSON.",
                max_tokens=900,
                temperature=0.4,
                use_small_model=True,  # cheap model — this runs a few times a day
            )
            if not response:
                return False

            text = response.strip()
            if "```" in text:
                import re
                text = re.sub(r"```(?:json)?", "", text).strip()
            start, end = text.find("{"), text.rfind("}")
            if start == -1 or end == -1:
                logger.warning("Intelligence: no JSON in update response")
                return False
            updated = json.loads(text[start:end + 1])
        except Exception as e:
            logger.warning(f"Intelligence: update parse failed: {e}")
            return False

        now = datetime.now(timezone.utc).isoformat()

        # Stamp narratives with last_seen and bound the lists
        narratives = updated.get("narratives", [])[:MAX_NARRATIVES]
        for n in narratives:
            n["last_seen"] = now
        self.brief["community_mood"] = str(updated.get("community_mood", ""))[:200]
        self.brief["narratives"] = narratives
        self.brief["alpha"] = [str(a)[:160] for a in updated.get("alpha", [])[:MAX_ALPHA]]
        self.brief["vocabulary"] = [str(v)[:40] for v in updated.get("vocabulary", [])[:MAX_VOCAB]]
        self.brief["watch"] = [str(w)[:120] for w in updated.get("watch", [])[:MAX_ALPHA]]
        self.brief["updated_at"] = now
        self.brief["processed_lines"] = getattr(self, "_pending_line_count", self.brief.get("processed_lines", 0))
        self._save()

        logger.info(
            f"Intelligence brief updated from {len(new_entries)} new entries "
            f"({len(self.brief['narratives'])} narratives, mood: {self.brief['community_mood'][:50]})"
        )
        return True

    # ------------------------------------------------------------------
    # Reading the brief for prompt injection
    # ------------------------------------------------------------------

    def get_brief_context(self, max_age_days: int = NARRATIVE_STALE_DAYS) -> Optional[str]:
        """
        Compact, injectable summary of what the bot has learned. Drops stale
        narratives. Returns None if the brief is empty. No API cost.
        """
        mood = self.brief.get("community_mood", "")
        narratives = self.brief.get("narratives", [])
        alpha = self.brief.get("alpha", [])
        vocab = self.brief.get("vocabulary", [])

        # Filter out stale narratives
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        fresh = []
        for n in narratives:
            ls = n.get("last_seen")
            try:
                if ls and datetime.fromisoformat(ls) < cutoff:
                    continue
            except ValueError:
                pass
            fresh.append(n)

        if not (mood or fresh or alpha or vocab):
            return None

        parts = ["WHAT YOU'VE LEARNED FROM WATCHING CT (use this to sound current and informed — weave in naturally, never recite it as a list):"]
        if mood:
            parts.append(f"- community mood: {mood}")
        if fresh:
            narr = "; ".join(
                f"{n.get('topic','?')} ({n.get('sentiment','?')}/{n.get('momentum','?')})"
                for n in fresh[:6]
            )
            parts.append(f"- live narratives: {narr}")
        if alpha:
            parts.append(f"- alpha worth knowing: {'; '.join(alpha[:4])}")
        if vocab:
            parts.append(f"- slang in play right now: {', '.join(vocab[:10])}")
        return "\n".join(parts)


# Module-level singleton so the generator, reply handlers, and background
# threads all share one brain (and one update cooldown).
_engine: Optional[IntelligenceEngine] = None
_engine_lock = threading.Lock()


def get_intelligence(claude_client=None) -> IntelligenceEngine:
    """Return the shared IntelligenceEngine, creating it on first call.
    Passing a claude_client wires up the update capability (safe to call
    repeatedly — the client is only set, never replaced with None)."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = IntelligenceEngine(claude_client=claude_client)
    if claude_client is not None and _engine.claude_client is None:
        _engine.claude_client = claude_client
    return _engine
