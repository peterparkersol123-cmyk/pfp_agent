"""
Helper utility functions for the AI agent.
"""

import re
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length, adding suffix if truncated.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def extract_hashtags(text: str) -> List[str]:
    """
    Extract hashtags from text.

    Args:
        text: Text containing hashtags

    Returns:
        List of hashtags (without #)
    """
    return re.findall(r'#(\w+)', text)


def count_hashtags(text: str) -> int:
    """
    Count number of hashtags in text.

    Args:
        text: Text to analyze

    Returns:
        Number of hashtags
    """
    return len(extract_hashtags(text))


def clean_text(text: str) -> str:
    """
    Clean text by removing extra whitespace and normalizing.

    Args:
        text: Text to clean

    Returns:
        Cleaned text
    """
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove leading/trailing whitespace
    text = text.strip()
    return text


def random_choice_weighted(choices: List[Dict[str, Any]], weight_key: str = "weight") -> Optional[Dict[str, Any]]:
    """
    Choose a random item from a list based on weights.

    Args:
        choices: List of dictionaries with weight key
        weight_key: Key name for weight value

    Returns:
        Selected choice or None if list is empty
    """
    if not choices:
        return None

    weights = [choice.get(weight_key, 1) for choice in choices]
    return random.choices(choices, weights=weights, k=1)[0]


def format_timestamp(dt: Optional[datetime] = None, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format a datetime object as a string.

    Args:
        dt: Datetime object (defaults to now)
        format_str: Format string

    Returns:
        Formatted timestamp
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime(format_str)


def time_until(target_time: datetime) -> str:
    """
    Get human-readable time until a target datetime.

    Args:
        target_time: Target datetime

    Returns:
        Human-readable time string
    """
    now = datetime.now()
    if target_time <= now:
        return "now"

    delta = target_time - now

    if delta.days > 0:
        return f"{delta.days}d {delta.seconds // 3600}h"
    elif delta.seconds >= 3600:
        return f"{delta.seconds // 3600}h {(delta.seconds % 3600) // 60}m"
    elif delta.seconds >= 60:
        return f"{delta.seconds // 60}m"
    else:
        return f"{delta.seconds}s"


def sanitize_for_twitter(text: str) -> str:
    """
    Sanitize text for Twitter posting.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text
    """
    # Clean text
    text = clean_text(text)

    # Remove any control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')

    return text


def calculate_exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Calculate exponential backoff delay.

    Args:
        attempt: Attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Delay in seconds
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    # Add jitter
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter
