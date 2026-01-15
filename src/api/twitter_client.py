"""
Twitter API client for posting content.
Handles communication with Twitter API v2.
"""

import os
import time
from typing import Optional, List, Dict, Any
import tweepy
from tweepy.errors import TweepyException, Forbidden, TooManyRequests, Unauthorized

from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.helpers import calculate_exponential_backoff, sanitize_for_twitter

logger = get_logger(__name__)


class TwitterClient:
    """Client for interacting with Twitter API v2."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
        bearer_token: Optional[str] = None
    ):
        """
        Initialize Twitter client.

        Args:
            api_key: Twitter API key
            api_secret: Twitter API secret
            access_token: Access token
            access_token_secret: Access token secret
            bearer_token: Bearer token
        """
        self.api_key = api_key or settings.TWITTER_API_KEY
        self.api_secret = api_secret or settings.TWITTER_API_SECRET
        self.access_token = access_token or settings.TWITTER_ACCESS_TOKEN
        self.access_token_secret = access_token_secret or settings.TWITTER_ACCESS_TOKEN_SECRET
        self.bearer_token = bearer_token or settings.TWITTER_BEARER_TOKEN

        # Initialize Tweepy client (OAuth 1.0a User Context)
        try:
            self.client = tweepy.Client(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                bearer_token=self.bearer_token,
                wait_on_rate_limit=True
            )
            logger.info("Initialized Twitter client successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Twitter client: {e}")
            raise

        self.max_tweet_length = settings.MAX_TWEET_LENGTH
        self.should_post = settings.should_post_to_twitter()

    def post_tweet(
        self,
        text: str,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Post a tweet to main timeline.

        Args:
            text: Tweet text
            max_retries: Maximum number of retry attempts

        Returns:
            Tweet data or None if failed
        """
        # Sanitize text
        text = sanitize_for_twitter(text)

        # Validate length
        if len(text) > self.max_tweet_length:
            logger.warning(f"Tweet exceeds max length ({len(text)} > {self.max_tweet_length})")
            text = text[:self.max_tweet_length - 3] + "..."

        # Debug mode - don't actually post
        if not self.should_post:
            logger.info(f"[DEBUG MODE] Would post tweet: {text[:100]}...")
            return {
                "id": "debug_tweet_id",
                "text": text,
                "debug": True
            }

        for attempt in range(max_retries):
            try:
                logger.debug(f"Posting tweet (attempt {attempt + 1}/{max_retries})")

                response = self.client.create_tweet(text=text)

                if response.data:
                    tweet_id = response.data['id']
                    logger.info(f"Successfully posted tweet (ID: {tweet_id})")
                    return {
                        "id": tweet_id,
                        "text": text,
                        "data": response.data
                    }
                else:
                    logger.warning("Received empty response from Twitter API")
                    return None

            except Forbidden as e:
                logger.error(f"Forbidden error (duplicate or policy violation): {e}")
                # Don't retry forbidden errors
                return None

            except Unauthorized as e:
                logger.error(f"Unauthorized error (check credentials): {e}")
                # Don't retry auth errors
                return None

            except TooManyRequests as e:
                logger.warning(f"Rate limit hit: {e}")
                if attempt < max_retries - 1:
                    delay = calculate_exponential_backoff(attempt, base_delay=60.0, max_delay=900.0)
                    logger.info(f"Waiting {delay:.1f}s before retry...")
                    time.sleep(delay)
                else:
                    logger.error("Max retries reached for rate limit")
                    return None

            except TweepyException as e:
                logger.error(f"Twitter API error: {e}")
                if attempt < max_retries - 1:
                    delay = calculate_exponential_backoff(attempt)
                    logger.info(f"Waiting {delay:.1f}s before retry...")
                    time.sleep(delay)
                else:
                    logger.error("Max retries reached for Twitter API error")
                    return None

            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                return None

        return None

    def post_thread(
        self,
        tweets: List[str],
        max_retries: int = 3
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Post a thread of tweets.

        Args:
            tweets: List of tweet texts
            max_retries: Maximum number of retry attempts

        Returns:
            List of tweet data or None if failed
        """
        if not tweets:
            logger.warning("No tweets provided for thread")
            return None

        logger.info(f"Posting thread with {len(tweets)} tweets")

        posted_tweets = []
        previous_tweet_id = None

        for i, tweet_text in enumerate(tweets):
            logger.debug(f"Posting tweet {i + 1}/{len(tweets)} in thread")

            # Sanitize text
            tweet_text = sanitize_for_twitter(tweet_text)

            # Debug mode
            if not self.should_post:
                logger.info(f"[DEBUG MODE] Would post thread tweet {i + 1}: {tweet_text[:100]}...")
                posted_tweets.append({
                    "id": f"debug_tweet_{i}",
                    "text": tweet_text,
                    "debug": True
                })
                previous_tweet_id = f"debug_tweet_{i}"
                continue

            for attempt in range(max_retries):
                try:
                    # Create tweet in reply to previous tweet
                    if previous_tweet_id:
                        response = self.client.create_tweet(
                            text=tweet_text,
                            in_reply_to_tweet_id=previous_tweet_id
                        )
                    else:
                        response = self.client.create_tweet(text=tweet_text)

                    if response.data:
                        tweet_id = response.data['id']
                        logger.info(f"Posted thread tweet {i + 1}/{len(tweets)} (ID: {tweet_id})")
                        posted_tweets.append({
                            "id": tweet_id,
                            "text": tweet_text,
                            "data": response.data
                        })
                        previous_tweet_id = tweet_id
                        break
                    else:
                        logger.warning(f"Empty response for thread tweet {i + 1}")
                        if attempt == max_retries - 1:
                            return None

                except Exception as e:
                    logger.error(f"Error posting thread tweet {i + 1}: {e}")
                    if attempt < max_retries - 1:
                        delay = calculate_exponential_backoff(attempt)
                        time.sleep(delay)
                    else:
                        logger.error(f"Failed to post complete thread after {i} tweets")
                        return None if not posted_tweets else posted_tweets

            # Small delay between thread tweets
            time.sleep(1)

        return posted_tweets

    def get_me(self) -> Optional[Dict[str, Any]]:
        """
        Get authenticated user information.

        Returns:
            User data or None if failed
        """
        try:
            response = self.client.get_me()
            if response.data:
                logger.info(f"Authenticated as: @{response.data.username}")
                return response.data
            return None
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None

    def test_connection(self) -> bool:
        """
        Test connection to Twitter API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info("Testing Twitter API connection...")
            user = self.get_me()
            if user:
                logger.info("Twitter API connection successful")
                return True
            else:
                logger.error("Twitter API connection failed - no user data")
                return False
        except Exception as e:
            logger.error(f"Twitter API connection test failed: {e}")
            return False
