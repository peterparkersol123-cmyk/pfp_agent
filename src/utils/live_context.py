"""
Compact live-market snapshot for reply prompts.

When someone asks the bot "what's the price?" or "how's volume?", the bot
should answer with real numbers, not vibes. This module builds a short
context block from free APIs (DexScreener + the staking API) and caches
it for 5 minutes so reply bursts cost zero extra requests.

No Claude API cost — this is pure data injection.
"""

import threading
import time
from typing import Optional

from src.utils.logger import get_logger
from src.utils.staking_tracker import get_tracker as get_staking_tracker

logger = get_logger(__name__)

_CACHE_TTL_SECONDS = 5 * 60

_lock = threading.Lock()
_cached_context: Optional[str] = None
_cached_at: float = 0.0
_pumpfun_client = None


def _get_client():
    global _pumpfun_client
    if _pumpfun_client is None:
        # Imported lazily to avoid a circular import at module load
        from src.api.pumpfun_client import PumpFunClient
        _pumpfun_client = PumpFunClient()
    return _pumpfun_client


def _fmt_usd(n: float) -> str:
    if n >= 1_000_000_000:
        return f"${n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"${n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n / 1_000:.1f}K"
    return f"${n:,.0f}"


def get_live_market_context() -> str:
    """
    Returns a compact LIVE MARKET DATA block for reply prompts, or '' if
    nothing could be fetched. Cached for 5 minutes.
    """
    global _cached_context, _cached_at

    with _lock:
        if _cached_context is not None and (time.time() - _cached_at) < _CACHE_TTL_SECONDS:
            return _cached_context

    parts = []
    try:
        pfp = _get_client().get_pfp_data()
        if pfp:
            parts.append(
                f"- $PFP price: ${pfp['price_usd']:.8f} "
                f"({pfp['price_change_24h']:+.1f}% 24h, {pfp['price_change_1h']:+.1f}% 1h)"
            )
            parts.append(
                f"- 24h volume: {_fmt_usd(pfp['volume_24h'])}, "
                f"market cap: {_fmt_usd(pfp['market_cap'])}, "
                f"liquidity: {_fmt_usd(pfp['liquidity'])}"
            )
    except Exception as e:
        logger.warning(f"Live context: could not fetch $PFP data: {e}")

    try:
        stats = get_staking_tracker().get_stats()
        if stats:
            total_staked = stats.get("totalStaked", 0)
            total_supply = stats.get("totalSupply", 0)
            stakers = stats.get("uniqueStakers", 0)
            holders = stats.get("totalHolders", 0)
            pct = (total_staked / total_supply * 100) if total_supply else 0
            parts.append(
                f"- Staking: {get_staking_tracker().get_staked_label()} pfp staked "
                f"({pct:.1f}% of supply), {stakers} stakers, {holders} holders"
            )
    except Exception as e:
        logger.warning(f"Live context: could not fetch staking stats: {e}")

    if parts:
        context = (
            "LIVE MARKET DATA (current, real - use these numbers if they ask "
            "about price/volume/mcap/staking, otherwise ignore):\n" + "\n".join(parts)
        )
    else:
        context = ""

    with _lock:
        _cached_context = context
        _cached_at = time.time()

    return context
