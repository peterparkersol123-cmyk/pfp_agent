"""
Single source of truth for pfp ecosystem knowledge.

Every prompt site (tweet templates, mention replies, comment replies,
account monitoring) pulls from here, so a fact only ever needs to be
updated in ONE place.

Hot-teaching without redeploy:
Drop one fact per line into DATA_DIR/extra_facts.txt (on the Railway
volume that's /data/extra_facts.txt). They are appended to the knowledge
block on the next prompt build — no code change, no redeploy. Example:

    new website is pfp.army
    gen3 nft mint announced for july

Lines starting with # are ignored.
"""

from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.staking_tracker import get_tracker as get_staking_tracker

logger = get_logger(__name__)

EXTRA_FACTS_FILE = settings.DATA_DIR / "extra_facts.txt"


def get_extra_facts() -> str:
    """Load operator-taught facts from the volume. Returns '' if none."""
    try:
        if not EXTRA_FACTS_FILE.exists():
            return ""
        lines = []
        for line in EXTRA_FACTS_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(f"- {line}")
        if not lines:
            return ""
        return "RECENTLY TAUGHT FACTS (operator-provided, treat as current truth):\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"Could not load extra facts: {e}")
        return ""


def get_shared_knowledge() -> str:
    """
    The canonical pfp knowledge block used by all reply/mention/monitor prompts.
    Includes the live staked amount and any operator-taught facts.
    """
    staked_label = get_staking_tracker().get_staked_label()

    knowledge = f"""KEY KNOWLEDGE:
- Website: https://pfp.army
- Contract: 5TfqNKZbn9AnNtzq8bbkyhKgcPGTfNDc9wNzFrTBpump
- Listed on MEXC, Moonshot, Jupiter
- THE FLYWHEEL (BIDIRECTIONAL, LIVE NOW):
  * Stake NFTs → Earn pfp every second (non-custodial, stays in your wallet)
  * Stake pfp → Earn NFTs (coin staking, non-custodial)
  * CTO wallet fees → buy pfp → add to staking rewards pool
- NFT Marketplace LIVE on pfp.army - buy/sell with SOL or any token, can open to other communities
- Built by @launchmynft
- {staked_label} pfp already staked - community conviction is real

ALLIED COMMUNITY - SOL PATRIOTS:
- Sol Patriots (solpatriots.com) = 9,999 NFTs on Solana, built by the SAME team (@launchmynft) as pfp
- Minted out in under 2 hours. Now trading on Magic Eden.
- STAKING: 9.9% royalty on every secondary sale, 100% goes to stakers in SOL. Zero team cut. Zero middleman.
- DAO: holders govern direction, partnerships, future drops
- Same builder, same community-first philosophy as pfp. Always positive about Sol Patriots - frens, not competition.

PUMP.FUN:
- pump.fun removed pfp Pepe as their OG default profile - erased the frog that built their brand
- Light roasting acceptable when it comes up naturally - always from a position of strength
- pfp built its own flywheel, its own marketplace - we don't need pump.fun"""

    extra = get_extra_facts()
    if extra:
        knowledge = f"{knowledge}\n\n{extra}"

    return knowledge
