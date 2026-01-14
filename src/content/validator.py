"""
Content validator for ensuring tweets meet requirements.
"""

import re
from typing import Tuple, List, Optional
from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.helpers import count_hashtags, extract_hashtags

logger = get_logger(__name__)


class ContentValidator:
    """Validates generated content before posting."""

    def __init__(self):
        """Initialize validator with settings."""
        self.max_length = settings.MAX_TWEET_LENGTH
        self.max_hashtags = settings.MAX_HASHTAGS
        self.use_hashtags = settings.USE_HASHTAGS

        # Prohibited content patterns
        self.prohibited_patterns = [
            r'\b(fuck|shit|damn)\b',  # Profanity
            r'\b(buy|sell|moon|wen)\s+(now|immediately)\b',  # Urgency/FOMO
            r'will\s+(hit|reach|go\s+to)\s+\$\d+',  # Price predictions (e.g., "will hit $100")
            r'\d+x\s+(gain|profit|return)',  # Return promises
            r'guaranteed|promise|definitely will',  # Guarantees
        ]

        # Required disclaimers for certain content
        self.financial_keywords = [
            'invest', 'trading', 'profit', 'gains', 'returns',
            'buy', 'sell', 'portfolio', 'strategy'
        ]

    def validate(self, content: str) -> Tuple[bool, List[str]]:
        """
        Validate content for posting.

        Args:
            content: Content to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check length
        if len(content) > self.max_length:
            errors.append(f"Content exceeds max length: {len(content)} > {self.max_length}")

        # Check for empty content
        if not content.strip():
            errors.append("Content is empty")

        # Check hashtag count
        hashtag_count = count_hashtags(content)
        if hashtag_count > self.max_hashtags:
            errors.append(f"Too many hashtags: {hashtag_count} > {self.max_hashtags}")

        # Check for prohibited content
        for pattern in self.prohibited_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                errors.append(f"Content contains prohibited pattern: {pattern}")

        # Check for financial advice without disclaimer
        has_financial_keywords = any(
            keyword in content.lower()
            for keyword in self.financial_keywords
        )
        has_disclaimer = 'NFA' in content or 'not financial advice' in content.lower()

        if has_financial_keywords and not has_disclaimer:
            logger.warning("Content contains financial keywords without disclaimer")
            # This is a warning, not an error

        # Check for URL safety
        if self._contains_suspicious_urls(content):
            errors.append("Content contains suspicious URLs")

        is_valid = len(errors) == 0
        return is_valid, errors

    def _contains_suspicious_urls(self, content: str) -> bool:
        """
        Check for suspicious URLs.

        Args:
            content: Content to check

        Returns:
            True if suspicious URLs found
        """
        # Extract URLs
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, content)

        # Check for known suspicious patterns
        suspicious_domains = [
            'bit.ly',  # Shortened URLs can be risky
            'tinyurl.com',
            't.co',  # Twitter's shortener is okay but check for others
        ]

        for url in urls:
            # Check for IP addresses instead of domains
            if re.search(r'http[s]?://\d+\.\d+\.\d+\.\d+', url):
                return True

            # Check for suspicious domains
            for domain in suspicious_domains:
                if domain in url.lower() and domain != 't.co':
                    return True

        return False

    def sanitize(self, content: str) -> str:
        """
        Sanitize content to make it valid.

        Args:
            content: Content to sanitize

        Returns:
            Sanitized content
        """
        # Truncate if too long
        if len(content) > self.max_length:
            content = content[:self.max_length - 3] + "..."

        # Remove excessive hashtags
        hashtags = extract_hashtags(content)
        if len(hashtags) > self.max_hashtags:
            # Remove extra hashtags from the end
            for hashtag in hashtags[self.max_hashtags:]:
                content = re.sub(f'#?{hashtag}\\s*', '', content, count=1)

        # Clean up whitespace
        content = re.sub(r'\s+', ' ', content).strip()

        return content

    def suggest_improvements(self, content: str) -> List[str]:
        """
        Suggest improvements for content.

        Args:
            content: Content to analyze

        Returns:
            List of suggestions
        """
        suggestions = []

        # Check hashtag usage
        hashtag_count = count_hashtags(content)
        if hashtag_count == 0 and self.use_hashtags:
            suggestions.append("Consider adding relevant hashtags (e.g., #Pumpfun, #Solana, #Crypto)")

        # Check for call to action
        cta_patterns = [
            r'\?$',  # Question
            r'!$',  # Exclamation
            r'\bcheck\s+out\b',
            r'\blearn\s+more\b',
            r'\bjoin\s+us\b',
        ]
        has_cta = any(re.search(pattern, content, re.IGNORECASE) for pattern in cta_patterns)
        if not has_cta:
            suggestions.append("Consider adding a call to action or question to drive engagement")

        # Check length utilization
        length_ratio = len(content) / self.max_length
        if length_ratio < 0.3:
            suggestions.append("Content is quite short - consider elaborating")

        # Check for emoji
        has_emoji = any(ord(char) > 127 for char in content)
        if not has_emoji:
            suggestions.append("Consider adding an emoji for visual appeal")

        return suggestions
