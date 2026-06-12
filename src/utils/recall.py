"""
Retrieval over the bot's learned knowledge (learned_context.jsonl).

The mention handler has been writing valuable conversation context to a
JSONL file — but nothing ever read it back when generating replies. This
module closes that loop with cheap keyword-overlap scoring: no embeddings,
no API calls, no cost.
"""

import json
import re
from typing import List, Optional

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

KNOWLEDGE_FILE = settings.DATA_DIR / "learned_context.jsonl"

# Words too common to signal relevance
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "is", "are", "was", "were", "this", "that", "it", "its", "with",
    "you", "your", "i", "my", "we", "our", "they", "their", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "can",
    "could", "should", "what", "when", "where", "who", "how", "why",
    "just", "not", "no", "so", "if", "as", "by", "from", "about", "all",
}


def _keywords(text: str) -> set:
    words = set(re.findall(r"\b[a-z0-9]{2,}\b", text.lower()))
    return words - _STOPWORDS


def recall_relevant_learnings(query_text: str, limit: int = 2, scan_last: int = 200) -> Optional[str]:
    """
    Find past learned conversations relevant to the given text.

    Args:
        query_text: The mention/comment we're replying to
        limit: Max learnings to return
        scan_last: Only scan the most recent N entries (keeps it fast)

    Returns:
        Formatted context block, or None if nothing relevant
    """
    try:
        if not KNOWLEDGE_FILE.exists():
            return None

        query_words = _keywords(query_text)
        if not query_words:
            return None

        with open(KNOWLEDGE_FILE, "r") as f:
            lines = f.readlines()[-scan_last:]

        scored = []
        for line in lines:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            content = f"{entry.get('original_tweet', '')} {entry.get('mention', '')}"
            entry_words = _keywords(content)
            if not entry_words:
                continue
            overlap = len(query_words & entry_words)
            # Require at least 2 meaningful shared words to count as relevant
            if overlap >= 2:
                scored.append((overlap, content.strip()))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [text[:200] for _, text in scored[:limit]]

        block = "RELEVANT PAST CONVERSATIONS (things you've seen the community discuss before):\n"
        block += "\n".join(f"- {t}" for t in top)
        logger.info(f"Recalled {len(top)} relevant learnings for reply context")
        return block

    except Exception as e:
        logger.warning(f"Recall failed: {e}")
        return None
