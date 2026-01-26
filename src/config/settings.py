"""
Configuration management for the AI agent.
Loads settings from environment variables and provides validation.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    """Application settings loaded from environment variables."""

    # Project paths
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"

    # Ensure directories exist
    DATA_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    # Claude API Configuration
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
    CLAUDE_MAX_TOKENS: int = int(os.getenv("CLAUDE_MAX_TOKENS", "1024"))
    CLAUDE_TEMPERATURE: float = float(os.getenv("CLAUDE_TEMPERATURE", "0.7"))
    CLAUDE_MAX_REQUESTS_PER_MINUTE: int = int(os.getenv("CLAUDE_MAX_REQUESTS_PER_MINUTE", "50"))

    # Twitter API Configuration
    TWITTER_API_KEY: str = os.getenv("TWITTER_API_KEY", "")
    TWITTER_API_SECRET: str = os.getenv("TWITTER_API_SECRET", "")
    TWITTER_ACCESS_TOKEN: str = os.getenv("TWITTER_ACCESS_TOKEN", "")
    TWITTER_ACCESS_TOKEN_SECRET: str = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
    TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")
    TWITTER_CLIENT_ID: str = os.getenv("TWITTER_CLIENT_ID", "")
    TWITTER_CLIENT_SECRET: str = os.getenv("TWITTER_CLIENT_SECRET", "")

    # Application Configuration
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # Posting Schedule
    POST_INTERVAL_MINUTES: int = int(os.getenv("POST_INTERVAL_MINUTES", "120"))
    MIN_INTERVAL_MINUTES: int = int(os.getenv("MIN_INTERVAL_MINUTES", "60"))
    MAX_INTERVAL_MINUTES: int = int(os.getenv("MAX_INTERVAL_MINUTES", "240"))

    # Content Configuration
    MAX_TWEET_LENGTH: int = int(os.getenv("MAX_TWEET_LENGTH", "280"))
    MAX_THREAD_TWEETS: int = int(os.getenv("MAX_THREAD_TWEETS", "5"))
    USE_HASHTAGS: bool = os.getenv("USE_HASHTAGS", "True").lower() == "true"
    MAX_HASHTAGS: int = int(os.getenv("MAX_HASHTAGS", "3"))

    # Rate Limiting
    TWITTER_MAX_TWEETS_PER_DAY: int = int(os.getenv("TWITTER_MAX_TWEETS_PER_DAY", "50"))
    TWITTER_MAX_TWEETS_PER_HOUR: int = int(os.getenv("TWITTER_MAX_TWEETS_PER_HOUR", "10"))

    # Blocklist - Users to never reply to or engage with
    BLOCKED_USERNAMES: set = {
        "armoskii",  # Requested to be blocked
        # Add more usernames here as needed (all lowercase)
    }

    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(DATA_DIR / "agent.db"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE_PATH: str = os.getenv("LOG_FILE_PATH", str(LOGS_DIR / "agent.log"))

    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """
        Validate that all required settings are present.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        if not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is not set")

        # Check Twitter credentials (at least one auth method)
        has_oauth1 = all([
            cls.TWITTER_API_KEY,
            cls.TWITTER_API_SECRET,
            cls.TWITTER_ACCESS_TOKEN,
            cls.TWITTER_ACCESS_TOKEN_SECRET
        ])
        has_oauth2 = cls.TWITTER_CLIENT_ID and cls.TWITTER_CLIENT_SECRET

        if not (has_oauth1 or has_oauth2):
            errors.append("Twitter API credentials are incomplete. Need either OAuth 1.0a or OAuth 2.0 credentials")

        if cls.POST_INTERVAL_MINUTES < cls.MIN_INTERVAL_MINUTES:
            errors.append(f"POST_INTERVAL_MINUTES ({cls.POST_INTERVAL_MINUTES}) must be >= MIN_INTERVAL_MINUTES ({cls.MIN_INTERVAL_MINUTES})")

        if cls.POST_INTERVAL_MINUTES > cls.MAX_INTERVAL_MINUTES:
            errors.append(f"POST_INTERVAL_MINUTES ({cls.POST_INTERVAL_MINUTES}) must be <= MAX_INTERVAL_MINUTES ({cls.MAX_INTERVAL_MINUTES})")

        return len(errors) == 0, errors

    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production environment."""
        return cls.ENVIRONMENT.lower() == "production"

    @classmethod
    def should_post_to_twitter(cls) -> bool:
        """Check if agent should actually post to Twitter (False in debug mode)."""
        return not cls.DEBUG


# Create a singleton instance
settings = Settings()
