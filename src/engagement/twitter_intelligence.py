"""
Twitter intelligence gathering for active learning.
Uses advanced search operators to find high-signal Pump.fun content.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from src.api.twitter_client import TwitterClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TwitterIntelligence:
    """
    Actively searches Twitter for high-signal Pump.fun content using
    advanced operators and filters inspired by professional sniper bots.
    """

    def __init__(self, twitter_client: Optional[TwitterClient] = None):
        """Initialize Twitter intelligence gatherer."""
        self.twitter_client = twitter_client or TwitterClient()
        logger.info("Initialized TwitterIntelligence")

    def build_advanced_search_query(
        self,
        base_terms: List[str],
        require_engagement: bool = True,
        min_likes: int = 20,
        exclude_spam: bool = True,
        include_media: bool = False,
        max_hours_old: int = 24
    ) -> str:
        """
        Build advanced Twitter search query using operators.

        Args:
            base_terms: Core search terms (e.g., ["pump.fun", "bonding curve"])
            require_engagement: Filter for minimum engagement
            min_likes: Minimum likes threshold
            exclude_spam: Add spam exclusions
            include_media: Require images/videos
            max_hours_old: Maximum tweet age in hours

        Returns:
            Advanced search query string
        """
        query_parts = []

        # Base terms (OR logic)
        if len(base_terms) > 1:
            base_query = "(" + " OR ".join(f'"{term}"' for term in base_terms) + ")"
        else:
            base_query = f'"{base_terms[0]}"'
        query_parts.append(base_query)

        # Engagement filter
        if require_engagement:
            query_parts.append(f"min_faves:{min_likes}")
            query_parts.append("min_retweets:5")

        # Spam exclusions
        if exclude_spam:
            spam_terms = [
                "dm me", "click here", "buy now", "airdrop now",
                "free mint", "join presale", "urgent buy"
            ]
            for term in spam_terms:
                query_parts.append(f'-"{term}"')

        # Media requirement
        if include_media:
            query_parts.append("filter:links OR filter:images")

        # Build final query
        query = " ".join(query_parts)

        logger.debug(f"Built search query: {query}")
        return query

    def search_pump_fun_intelligence(
        self,
        focus: str = "general",
        max_results: int = 20
    ) -> List[Dict]:
        """
        Search for high-signal Pump.fun content based on focus area.

        Args:
            focus: Type of intelligence ("general", "launches", "narratives", "safety")
            max_results: Maximum tweets to return

        Returns:
            List of tweet data dicts
        """
        try:
            # Define search strategies by focus
            search_configs = {
                "general": {
                    "base_terms": ["pump.fun", "pumpfun"],
                    "min_likes": 20,
                },
                "launches": {
                    "base_terms": ["pump.fun launch", "bonding curve", "curve complete"],
                    "min_likes": 30,
                    "include_media": True,
                },
                "narratives": {
                    "base_terms": ["pump.fun", "ai agent", "meta", "narrative shift"],
                    "min_likes": 50,
                },
                "safety": {
                    "base_terms": ["pump.fun", "dev burn", "mint revoked", "rug"],
                    "min_likes": 15,
                },
                "whale_activity": {
                    "base_terms": ["pump.fun", "whale buy", "smart money", "deployer"],
                    "min_likes": 40,
                }
            }

            config = search_configs.get(focus, search_configs["general"])

            # Build query
            query = self.build_advanced_search_query(**config)

            # Search Twitter
            logger.info(f"Searching for {focus} intelligence...")

            response = self.twitter_client.client.search_recent_tweets(
                query=query,
                max_results=min(max_results, 100),  # API limit
                tweet_fields=['created_at', 'public_metrics', 'author_id'],
                expansions=['author_id'],
                user_fields=['username', 'public_metrics'],
                user_auth=True
            )

            if not response.data:
                logger.info(f"No tweets found for {focus} search")
                return []

            # Format results
            tweets = []
            users_dict = {}
            if response.includes and 'users' in response.includes:
                users_dict = {user.id: user for user in response.includes['users']}

            for tweet in response.data:
                author = users_dict.get(tweet.author_id)
                if not author:
                    continue

                tweets.append({
                    'id': tweet.id,
                    'text': tweet.text,
                    'author_username': author.username,
                    'author_followers': author.public_metrics.get('followers_count', 0),
                    'likes': tweet.public_metrics.get('like_count', 0),
                    'retweets': tweet.public_metrics.get('retweet_count', 0),
                    'created_at': tweet.created_at,
                })

            logger.info(f"Found {len(tweets)} high-signal tweets for {focus}")
            return tweets

        except Exception as e:
            logger.error(f"Error searching for intelligence: {e}")
            return []

    def get_trending_narratives(self) -> List[str]:
        """
        Actively search for emerging narratives and trends.

        Returns:
            List of narrative insights
        """
        try:
            # Search for narrative discussions
            tweets = self.search_pump_fun_intelligence(focus="narratives", max_results=30)

            if not tweets:
                return []

            # Extract common themes (simple keyword frequency)
            text_corpus = " ".join(tweet['text'].lower() for tweet in tweets)

            # Key narrative terms to track
            narrative_keywords = {
                'ai agent': 'ai agent meta',
                'depin': 'depin narrative',
                'meme season': 'meme rotation',
                'cat': 'cat meta',
                'dog': 'dog meta',
                'gaming': 'gaming tokens',
                'utility': 'utility over meme',
            }

            detected_narratives = []
            for keyword, narrative in narrative_keywords.items():
                if keyword in text_corpus:
                    # Count frequency
                    count = text_corpus.count(keyword)
                    if count >= 3:  # Mentioned in at least 3 tweets
                        detected_narratives.append(f"{narrative} ({count} mentions)")

            logger.info(f"Detected {len(detected_narratives)} trending narratives")
            return detected_narratives

        except Exception as e:
            logger.error(f"Error detecting narratives: {e}")
            return []
