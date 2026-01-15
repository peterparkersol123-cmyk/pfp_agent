"""
Engagement tracking system to monitor tweet performance and learn from successful content.
"""

import time
from typing import Dict, List, Optional
from datetime import datetime, timezone
from src.api.twitter_client import TwitterClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EngagementTracker:
    """Tracks engagement metrics for tweets and identifies high-performing content."""

    def __init__(self, twitter_client: Optional[TwitterClient] = None):
        """
        Initialize engagement tracker.

        Args:
            twitter_client: Twitter API client (creates new one if not provided)
        """
        self.twitter_client = twitter_client or TwitterClient()
        self.tracked_tweets: Dict[str, Dict] = {}  # tweet_id -> metrics
        logger.info("Initialized EngagementTracker")

    def track_tweet(self, tweet_id: str, tweet_text: str) -> None:
        """
        Start tracking a tweet's engagement.

        Args:
            tweet_id: Twitter tweet ID
            tweet_text: Full text of the tweet
        """
        self.tracked_tweets[tweet_id] = {
            'text': tweet_text,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'likes': 0,
            'retweets': 0,
            'replies': 0,
            'impressions': 0,
            'last_updated': None
        }
        logger.info(f"Started tracking tweet {tweet_id}")

    def update_metrics(self, tweet_id: str) -> Optional[Dict]:
        """
        Fetch and update engagement metrics for a tweet.

        Args:
            tweet_id: Twitter tweet ID

        Returns:
            Updated metrics dict or None if failed
        """
        try:
            # Fetch tweet metrics from Twitter API
            tweet = self.twitter_client.client.get_tweet(
                id=tweet_id,
                tweet_fields=['public_metrics', 'created_at'],
                user_auth=True
            )

            if not tweet.data:
                logger.warning(f"Could not fetch metrics for tweet {tweet_id}")
                return None

            metrics = tweet.data.public_metrics

            # Update tracked metrics
            if tweet_id in self.tracked_tweets:
                self.tracked_tweets[tweet_id].update({
                    'likes': metrics.get('like_count', 0),
                    'retweets': metrics.get('retweet_count', 0),
                    'replies': metrics.get('reply_count', 0),
                    'impressions': metrics.get('impression_count', 0),
                    'last_updated': datetime.now(timezone.utc).isoformat()
                })

                logger.info(f"Updated metrics for {tweet_id}: {metrics.get('like_count', 0)} likes, {metrics.get('retweet_count', 0)} RTs, {metrics.get('reply_count', 0)} replies")
                return self.tracked_tweets[tweet_id]

        except Exception as e:
            logger.error(f"Error updating metrics for tweet {tweet_id}: {e}")

        return None

    def get_engagement_score(self, tweet_id: str) -> float:
        """
        Calculate engagement score for a tweet.
        Formula: (likes * 1) + (retweets * 3) + (replies * 2)

        Args:
            tweet_id: Twitter tweet ID

        Returns:
            Engagement score (higher is better)
        """
        if tweet_id not in self.tracked_tweets:
            return 0.0

        metrics = self.tracked_tweets[tweet_id]
        score = (
            metrics['likes'] * 1.0 +
            metrics['retweets'] * 3.0 +
            metrics['replies'] * 2.0
        )
        return score

    def get_top_performing_tweets(self, limit: int = 5) -> List[Dict]:
        """
        Get top performing tweets based on engagement score.

        Args:
            limit: Number of top tweets to return

        Returns:
            List of tweet dicts sorted by engagement score
        """
        # Update metrics for all tracked tweets
        for tweet_id in list(self.tracked_tweets.keys()):
            self.update_metrics(tweet_id)
            time.sleep(1)  # Rate limiting

        # Calculate scores and sort
        scored_tweets = []
        for tweet_id, data in self.tracked_tweets.items():
            score = self.get_engagement_score(tweet_id)
            scored_tweets.append({
                'tweet_id': tweet_id,
                'text': data['text'],
                'score': score,
                'metrics': data
            })

        scored_tweets.sort(key=lambda x: x['score'], reverse=True)
        return scored_tweets[:limit]

    def get_successful_patterns(self) -> str:
        """
        Analyze top tweets and extract successful patterns.

        Returns:
            Text summary of what works well
        """
        top_tweets = self.get_top_performing_tweets(limit=5)

        if not top_tweets:
            return "No engagement data available yet."

        patterns = ["Recent high-performing tweets:"]
        for i, tweet in enumerate(top_tweets, 1):
            score = tweet['score']
            text = tweet['text'][:100]
            patterns.append(f"{i}. (score: {score:.0f}) \"{text}...\"")

        return "\n".join(patterns)

    def should_adjust_style(self) -> bool:
        """
        Determine if style adjustment is needed based on engagement.

        Returns:
            True if engagement is consistently low
        """
        if len(self.tracked_tweets) < 5:
            return False  # Need more data

        # Calculate average engagement
        recent_tweets = list(self.tracked_tweets.values())[-5:]
        avg_likes = sum(t['likes'] for t in recent_tweets) / len(recent_tweets)

        # If average likes < 5, might need adjustment
        return avg_likes < 5.0

    def cleanup_old_tweets(self, days_old: int = 7) -> None:
        """
        Remove tracked tweets older than specified days.

        Args:
            days_old: Remove tweets older than this many days
        """
        now = datetime.now(timezone.utc)
        to_remove = []

        for tweet_id, data in self.tracked_tweets.items():
            created_at = datetime.fromisoformat(data['created_at'])
            age_days = (now - created_at).days

            if age_days > days_old:
                to_remove.append(tweet_id)

        for tweet_id in to_remove:
            del self.tracked_tweets[tweet_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old tracked tweets")
