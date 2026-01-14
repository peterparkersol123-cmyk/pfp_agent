"""
Database models/schemas for the agent.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Post:
    """Represents a posted tweet."""
    id: Optional[int] = None
    tweet_id: Optional[str] = None
    content: str = ""
    content_type: str = "general"
    status: str = "pending"  # pending, posted, failed
    created_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    is_thread: bool = False
    thread_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class Topic:
    """Represents a content topic with usage tracking."""
    id: Optional[int] = None
    topic_name: str = ""
    content_type: str = "general"
    last_used: Optional[datetime] = None
    usage_count: int = 0
    success_rate: float = 0.0  # Percentage of successful posts
    avg_engagement: float = 0.0  # Average likes + retweets


@dataclass
class Setting:
    """Represents a configuration setting."""
    id: Optional[int] = None
    key: str = ""
    value: str = ""
    updated_at: Optional[datetime] = None
