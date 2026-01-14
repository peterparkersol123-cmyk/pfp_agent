"""
Topic manager for intelligent topic selection and rotation.
"""

import random
from datetime import datetime, timedelta
from typing import List, Optional
from src.content.templates import ContentType
from src.database.operations import DatabaseManager
from src.database.models import Topic
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TopicManager:
    """Manages topic selection and rotation to avoid repetition."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize topic manager.

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager or DatabaseManager()
        logger.info("Initialized TopicManager")

    def select_content_type(self) -> ContentType:
        """
        Select a content type based on usage history.

        Returns:
            Selected ContentType
        """
        # Get all content types
        all_types = list(ContentType)

        # Get usage statistics for each type
        type_weights = {}

        for content_type in all_types:
            # Check when this type was last used
            topic = self.db.get_topic(content_type.value)

            if topic and topic.last_used:
                # Calculate weight based on time since last use
                hours_since = (datetime.now() - topic.last_used).total_seconds() / 3600

                # Weight increases with time (prefer less recently used)
                # Minimum weight of 1, increases by 1 for every 2 hours
                weight = max(1, int(hours_since / 2))

                # Boost weight for successful topics
                if topic.success_rate > 0.8:
                    weight = int(weight * 1.5)
            else:
                # Never used, give high weight
                weight = 10

            type_weights[content_type] = weight

        logger.debug(f"Content type weights: {type_weights}")

        # Weighted random selection
        content_types = list(type_weights.keys())
        weights = list(type_weights.values())

        selected = random.choices(content_types, weights=weights, k=1)[0]
        logger.info(f"Selected content type: {selected.value}")

        # Update topic usage
        self._update_topic_usage(selected.value)

        return selected

    def should_post_thread(self) -> bool:
        """
        Decide whether to post a thread instead of a single tweet.

        Returns:
            True if should post thread
        """
        # Get recent posts
        recent_posts = self.db.get_recent_posts(limit=10, status="posted")

        # Count threads in recent posts
        thread_count = sum(1 for post in recent_posts if post.is_thread)

        # Target: ~20% of posts should be threads
        thread_probability = 0.2

        # Adjust probability based on recent threads
        if thread_count > 3:  # Too many threads recently
            thread_probability = 0.1
        elif thread_count == 0:  # No threads recently
            thread_probability = 0.4

        should_thread = random.random() < thread_probability
        logger.debug(f"Thread decision: {should_thread} (recent threads: {thread_count}/10)")

        return should_thread

    def get_posting_time_recommendation(self) -> str:
        """
        Get recommendation for optimal posting time.

        Returns:
            Human-readable recommendation
        """
        current_hour = datetime.now().hour

        # Optimal posting hours for crypto content (UTC)
        # Peak times: 13-17 UTC (9am-1pm ET) and 1-5 UTC (9pm-1am ET)
        optimal_hours = [1, 2, 3, 4, 13, 14, 15, 16, 17]
        good_hours = [0, 5, 12, 18, 19, 20, 21, 22]

        if current_hour in optimal_hours:
            return "optimal"
        elif current_hour in good_hours:
            return "good"
        else:
            return "okay"

    def _update_topic_usage(self, topic_name: str):
        """Update topic usage statistics."""
        topic = self.db.get_topic(topic_name)

        if topic:
            topic.last_used = datetime.now()
            topic.usage_count += 1
        else:
            topic = Topic(
                topic_name=topic_name,
                content_type=topic_name,
                last_used=datetime.now(),
                usage_count=1
            )

        self.db.create_or_update_topic(topic)
        logger.debug(f"Updated topic usage: {topic_name}")

    def update_topic_success(self, topic_name: str, success: bool, engagement: int = 0):
        """
        Update topic success metrics.

        Args:
            topic_name: Topic name
            success: Whether post was successful
            engagement: Engagement score (likes + retweets + replies)
        """
        topic = self.db.get_topic(topic_name)

        if not topic:
            logger.warning(f"Topic not found: {topic_name}")
            return

        # Update success rate
        total_posts = topic.usage_count
        current_successes = topic.success_rate * total_posts
        new_successes = current_successes + (1 if success else 0)
        topic.success_rate = new_successes / total_posts

        # Update average engagement
        current_total_engagement = topic.avg_engagement * total_posts
        new_total_engagement = current_total_engagement + engagement
        topic.avg_engagement = new_total_engagement / total_posts

        self.db.create_or_update_topic(topic)
        logger.debug(f"Updated topic metrics: {topic_name} (success rate: {topic.success_rate:.2%})")

    def get_topic_insights(self) -> dict:
        """
        Get insights about topic performance.

        Returns:
            Dictionary with topic insights
        """
        least_used = self.db.get_least_used_topics(limit=5)

        insights = {
            "least_used_topics": [
                {
                    "name": topic.topic_name,
                    "usage_count": topic.usage_count,
                    "last_used": topic.last_used.isoformat() if topic.last_used else None
                }
                for topic in least_used
            ]
        }

        return insights
