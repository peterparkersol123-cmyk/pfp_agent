"""
Self-critique system for tweet quality control.
Ensures only high-quality, on-brand tweets are posted.
"""

from typing import Optional, Tuple
from src.api.claude_client import ClaudeClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TweetCritic:
    """Critiques generated tweets for quality before posting."""

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        """
        Initialize tweet critic.

        Args:
            claude_client: Claude API client (creates new one if not provided)
        """
        self.claude_client = claude_client or ClaudeClient()
        logger.info("Initialized TweetCritic")

    def critique_tweet(self, tweet: str) -> Tuple[int, str]:
        """
        Rate tweet 1-10 and suggest improvements.

        Args:
            tweet: Generated tweet text

        Returns:
            (score, feedback) tuple where score is 1-10
        """
        try:
            prompt = f"""You are Pepe's inner critic. Rate this tweet 1-10:

TWEET: "{tweet}"

Rate on:
1. Pepe energy (frog cult / degen wisdom) - is it authentic?
2. Freshness (not generic, not repetitive)
3. Engagement potential (rage-bait / quotable)
4. Pump.fun math flex (if relevant)
5. $PFP positivity (if mentioned)

Respond in this format:
Score: [1-10]
Why: [one line explanation]
Fix: [specific improvement if <8, or "ship it" if >=8]"""

            system_prompt = """You are a brutal but fair tweet critic. You know what makes Pepe tweets legendary vs generic. Be honest, concise.

Judge tweets on:
- Authentic degen Pepe energy (not corporate AI speak)
- Fresh angles (not repetitive or cliche)
- Engagement hooks (quotable, rage-bait worthy, screenshot material)
- Technical depth when relevant (bonding curves, volume, etc)
- Unwavering $PFP positivity if the token is mentioned

You reject:
- Generic AI voice ("just tried...", "i really like...")
- Corporate speak or boring takes
- Weak energy or lukewarm vibes
- Anything that sounds like a brand account
- Negative $PFP sentiment

You approve:
- Raw, unhinged degen truth bombs
- Smart observations wrapped in chaos
- Quotable one-liners
- Authentic Pepe personality
- Pure bullish $PFP energy"""

            response = self.claude_client.generate_content(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=100,
                temperature=0.3  # Lower temp for consistent critique
            )

            if not response:
                logger.warning("Critique failed, defaulting to acceptable score")
                return (7, "Critique failed, defaulting to acceptable")

            # Parse score
            score = 7  # Default
            if "Score:" in response:
                score_line = response.split("Score:")[1].split("\n")[0]
                try:
                    # Extract just the number
                    score_str = ''.join(filter(str.isdigit, score_line))[:2]
                    if score_str:
                        score = int(score_str)
                        score = max(1, min(10, score))  # Clamp 1-10
                except ValueError:
                    logger.warning(f"Could not parse score from: {score_line}")
                    score = 7

            logger.info(f"Tweet critique: {score}/10")
            logger.debug(f"Critique feedback: {response}")
            return (score, response)

        except Exception as e:
            logger.error(f"Error critiquing tweet: {e}", exc_info=True)
            return (7, "Critique error, accepting tweet")
