"""
Engagement tracking system to monitor tweet performance and learn from successful content.
"""

import json
import os
from pathlib import Path
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

        # Persist engagement data to disk so style learning survives restarts
        data_dir = os.getenv("DATA_DIR", "data")
        self._data_file = Path(data_dir) / "engagement_data.json"
        self._data_file.parent.mkdir(parents=True, exist_ok=True)

        self.tracked_tweets: Dict[str, Dict] = self._load()
        logger.info(f"Initialized EngagementTracker — loaded {len(self.tracked_tweets)} tracked tweets from disk")

    def _load(self) -> Dict[str, Dict]:
        """Load persisted engagement data from disk."""
        try:
            if self._data_file.exists():
                with open(self._data_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading engagement data: {e}")
        return {}

    def _save(self) -> None:
        """Atomically save engagement data to disk."""
        try:
            tmp = self._data_file.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(self.tracked_tweets, f, indent=2, default=str)
            os.replace(tmp, self._data_file)
        except Exception as e:
            logger.error(f"Error saving engagement data: {e}")

    def track_tweet(self, tweet_id: str, tweet_text: str, content_type: Optional[str] = None) -> None:
        """
        Start tracking a tweet's engagement.

        Args:
            tweet_id: Twitter tweet ID
            tweet_text: Full text of the tweet
            content_type: ContentType value the tweet was generated from
                (enables per-topic performance learning)
        """
        self.tracked_tweets[tweet_id] = {
            'text': tweet_text,
            'content_type': content_type,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'likes': 0,
            'retweets': 0,
            'replies': 0,
            'impressions': 0,
            'last_updated': None
        }
        self._save()
        logger.info(f"Started tracking tweet {tweet_id} (type: {content_type})")

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
                self._save()
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

    def update_metrics_batch(self, tweet_ids: List[str]) -> int:
        """
        Fetch and update metrics for up to 100 tweets in a single X API read
        (vs one read per tweet with update_metrics).

        Args:
            tweet_ids: Tweet IDs to refresh

        Returns:
            Number of tracked tweets updated
        """
        ids = [str(tid) for tid in tweet_ids if tid][:100]
        if not ids:
            return 0

        try:
            response = self.twitter_client.client.get_tweets(
                ids=ids,
                tweet_fields=['public_metrics'],
                user_auth=True
            )
        except Exception as e:
            logger.error(f"Error batch-fetching metrics for {len(ids)} tweets: {e}")
            return 0

        updated = 0
        for tweet in (response.data or []):
            tweet_id = str(tweet.id)
            if tweet_id not in self.tracked_tweets:
                continue
            metrics = tweet.public_metrics
            self.tracked_tweets[tweet_id].update({
                'likes': metrics.get('like_count', 0),
                'retweets': metrics.get('retweet_count', 0),
                'replies': metrics.get('reply_count', 0),
                'impressions': metrics.get('impression_count', 0),
                'last_updated': datetime.now(timezone.utc).isoformat()
            })
            updated += 1

        if updated:
            self._save()
            logger.info(f"Batch-updated metrics for {updated} tweets in one API call")
        return updated

    def get_top_performing_tweets(self, limit: int = 5) -> List[Dict]:
        """
        Get top performing tweets based on engagement score.

        Uses cached metrics only — refresh via update_metrics_batch() in the
        posting cycle. This method is called on every generation attempt for
        style learning, so fetching from X here would burn one read per
        tracked tweet per attempt.

        Args:
            limit: Number of top tweets to return

        Returns:
            List of tweet dicts sorted by engagement score
        """
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

    def get_bottom_performing_tweets(self, limit: int = 3) -> List[Dict]:
        """
        Get the lowest-scoring tweets whose metrics have actually been fetched
        (a tweet that was never measured would score a meaningless 0).
        Used as negative examples for style learning.

        Args:
            limit: Number of bottom tweets to return

        Returns:
            List of tweet dicts sorted by engagement score ascending
        """
        scored_tweets = []
        for tweet_id, data in self.tracked_tweets.items():
            if not data.get('last_updated'):
                continue
            scored_tweets.append({
                'tweet_id': tweet_id,
                'text': data['text'],
                'score': self.get_engagement_score(tweet_id),
                'metrics': data
            })

        scored_tweets.sort(key=lambda x: x['score'])
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

    def get_content_type_multipliers(self) -> Dict[str, float]:
        """
        Learn which content types perform: compute a weight multiplier per
        content type based on average engagement vs the overall average.

        Multipliers are clamped to [0.5, 2.0] so no topic ever fully dies
        or completely dominates. Types with fewer than 2 tracked tweets get
        no adjustment (not enough signal).

        Returns:
            Dict of content_type value -> multiplier. Empty if not enough data.
        """
        # Group scores by content type (uses cached metrics — no API calls)
        by_type: Dict[str, List[float]] = {}
        all_scores: List[float] = []
        for tweet_id, data in self.tracked_tweets.items():
            ctype = data.get('content_type')
            if not ctype:
                continue
            score = self.get_engagement_score(tweet_id)
            by_type.setdefault(ctype, []).append(score)
            all_scores.append(score)

        if len(all_scores) < 5:
            return {}  # Not enough data to learn from yet

        overall_avg = sum(all_scores) / len(all_scores)
        if overall_avg <= 0:
            return {}

        multipliers = {}
        for ctype, scores in by_type.items():
            if len(scores) < 2:
                continue
            type_avg = sum(scores) / len(scores)
            multiplier = type_avg / overall_avg
            multipliers[ctype] = max(0.5, min(2.0, multiplier))

        if multipliers:
            logger.info(f"Content type performance multipliers: { {k: round(v, 2) for k, v in multipliers.items()} }")
        return multipliers

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
            self._save()
            logger.info(f"Cleaned up {len(to_remove)} old tracked tweets")
