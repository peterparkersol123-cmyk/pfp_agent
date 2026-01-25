"""
Content generator that uses Claude API to create tweets with real-time ecosystem data.
"""

import random
import re
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from src.api.claude_client import ClaudeClient
from src.api.pumpfun_client import PumpFunClient
from src.content.templates import PromptTemplates, ContentTemplate, ContentType
from src.content.validator import ContentValidator
from src.content.critic import TweetCritic
from src.utils.logger import get_logger
from src.utils.helpers import random_choice_weighted
from src.utils.price_mention_tracker import PriceMentionTracker

logger = get_logger(__name__)


class ContentGenerator:
    """Generates content using Claude API with real-time Pump.fun ecosystem data."""

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        pumpfun_client: Optional[PumpFunClient] = None,
        topic_history_size: int = 5
    ):
        """
        Initialize content generator.

        Args:
            claude_client: Claude API client (creates new one if not provided)
            pumpfun_client: Pump.fun API client (creates new one if not provided)
            topic_history_size: Number of recent topics to track for variety
        """
        self.claude_client = claude_client or ClaudeClient()
        self.pumpfun_client = pumpfun_client or PumpFunClient()
        self.validator = ContentValidator()
        self.templates = PromptTemplates()
        self.critic = TweetCritic(claude_client)
        self.price_tracker = PriceMentionTracker()

        # Track recent content types for variety
        self.recent_topics: List[ContentType] = []
        self.topic_history_size = topic_history_size

        # Track when "gm" was last used (date only, UTC)
        self.last_gm_date: Optional[str] = None

        # Track last 10 tweets to avoid repetitive content
        self.recent_tweets: List[str] = []
        self.recent_tweets_limit = 10

        # Knowledge base for learned context
        self.knowledge_file = Path("data/learned_context.jsonl")

        logger.info("Initialized ContentGenerator with Pump.fun data integration")

    def _build_ecosystem_context(self) -> str:
        """
        Build context string with real-time Pump.fun ecosystem data.

        Returns:
            Formatted context string for Claude
        """
        try:
            logger.debug("Fetching ecosystem data for context")
            context_data = self.pumpfun_client.get_context_for_content()

            context_parts = ["Current Pump.fun ecosystem context:"]

            # Add $PFP data FIRST (most important)
            pfp_data = context_data.get('pfp_data')
            if pfp_data:
                price = pfp_data.get('price_usd', 0)
                change_24h = pfp_data.get('price_change_24h', 0)
                volume_24h = pfp_data.get('volume_24h', 0)

                change_dir = "up" if change_24h > 0 else "down"
                context_parts.append(f"- YOUR TOKEN $PFP: ${price:.8f} ({change_24h:+.2f}% 24h {change_dir}), ${volume_24h:,.0f} volume")
                context_parts.append(f"  Chart: https://dexscreener.com/solana/gdfcd7l8x1giudfz1wthnheb352k3ni37rswtjgmglpt")

            # Add narrative
            if context_data.get('narrative'):
                context_parts.append(f"- Current meta: {context_data['narrative']}")

            # Add trending tokens
            trending = context_data.get('trending_tokens', [])[:3]
            if trending:
                context_parts.append("- Trending tokens:")
                for token in trending:
                    name = token.get('name', 'Unknown')
                    symbol = token.get('symbol', '???')
                    context_parts.append(f"  * {name} (${symbol})")

            # Add recent launches
            recent = context_data.get('recent_launches', [])[:3]
            if recent:
                context_parts.append("- Recent launches:")
                for token in recent:
                    name = token.get('name', 'Unknown')
                    context_parts.append(f"  * {name}")

            # Add rug alerts
            rugs = context_data.get('suspicious_activity', [])
            if rugs:
                context_parts.append(f"- {len(rugs)} suspicious tokens detected in last 24h")

            # Add platform stats
            stats = context_data.get('platform_stats', {})
            if stats and stats.get('total_tokens'):
                context_parts.append(f"- Platform: {stats.get('total_tokens', '???')} tokens, ${stats.get('volume_24h', '???')} 24h volume")

            context_str = "\n".join(context_parts)
            logger.debug("Built ecosystem context")
            return context_str

        except Exception as e:
            logger.error(f"Error building ecosystem context: {e}")
            return "Current Pump.fun ecosystem: live data unavailable, use general knowledge"

    def _extract_insights_from_learnings(self, learnings: List[Dict]) -> Optional[str]:
        """
        Use Claude to extract actionable insights from learned conversations.
        This makes learning ACTIVE instead of passive.

        Args:
            learnings: List of learned conversation entries

        Returns:
            Extracted insights or None
        """
        try:
            if not learnings:
                return None

            # Format learnings for Claude
            conversations = []
            for i, learning in enumerate(learnings[-10:], 1):  # Last 10 max
                original = learning.get('original_tweet', '')
                if original and len(original) > 10:
                    conversations.append(f"{i}. {original}")

            if not conversations:
                return None

            conversations_text = "\n".join(conversations)

            # Ask Claude to extract insights
            prompt = f"""You've been exposed to these recent tweets through conversations:

{conversations_text}

Extract 2-3 KEY INSIGHTS or LEARNINGS from these tweets that would be valuable for a Pump.fun Pepe character to know. Focus on:
- New tokens, narratives, or trends mentioned
- Market sentiment or price action insights
- Cultural shifts or memes emerging
- Alpha or knowledge worth remembering

Format as bullet points, very concise (1 line each), in lowercase degen style.
Example: "- traders rotating into ai agent tokens, narrative heating up"

Insights:"""

            system_prompt = """You extract actionable insights from tweets. Be concise, focus on market-relevant information, trends, narratives, new tokens, or cultural shifts. Write in lowercase degen style."""

            insights = self.claude_client.generate_content(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=150,
                temperature=0.7
            )

            if insights:
                insights = insights.strip()
                logger.info(f"Extracted insights from {len(conversations)} learnings")
                return insights

            return None

        except Exception as e:
            logger.error(f"Error extracting insights: {e}")
            return None

    def _get_learned_context(self, limit: int = 5) -> Optional[str]:
        """
        Get recent learned context from mentions/conversations.
        Extracts INSIGHTS instead of raw tweets for better learning.

        Args:
            limit: Number of recent learnings to check

        Returns:
            Formatted learned insights or None
        """
        try:
            if not self.knowledge_file.exists():
                return None

            # Read recent learnings
            learnings = []
            with open(self.knowledge_file, 'r') as f:
                lines = f.readlines()
                for line in lines[-20:]:  # Check last 20
                    try:
                        entry = json.loads(line.strip())
                        learnings.append(entry)
                    except:
                        continue

            if not learnings:
                return None

            # Extract insights using Claude (smart learning)
            insights = self._extract_insights_from_learnings(learnings)

            if insights:
                formatted = f"RECENT LEARNINGS from community conversations:\n{insights}"
                logger.debug(f"Loaded insights from {len(learnings)} conversations")
                return formatted

            return None

        except Exception as e:
            logger.error(f"Error loading learned context: {e}")
            return None

    def generate_tweet(
        self,
        content_type: Optional[ContentType] = None,
        custom_prompt: Optional[str] = None,
        max_attempts: int = 10,
        use_live_data: bool = True,
        engagement_tracker=None
    ) -> Optional[str]:
        """
        Generate a single tweet with optional live ecosystem data.

        Args:
            content_type: Type of content to generate (random if not specified)
            custom_prompt: Custom prompt to use instead of templates
            max_attempts: Maximum attempts to generate valid content
            use_live_data: Whether to include live Pump.fun data in context
            engagement_tracker: Optional engagement tracker for style learning

        Returns:
            Generated tweet text or None if failed
        """
        for attempt in range(max_attempts):
            try:
                logger.debug(f"Generating tweet (attempt {attempt + 1}/{max_attempts})")

                # Select template or use custom prompt
                if custom_prompt:
                    system_prompt = self.templates.BASE_SYSTEM_PROMPT
                    user_prompt = custom_prompt
                else:
                    template = self._select_template(content_type)
                    system_prompt = template.system_prompt
                    user_prompt = random.choice(template.user_prompts)

                    # Add live data context for relevant content types
                    if use_live_data and self._should_use_live_data(template.content_type):
                        ecosystem_context = self._build_ecosystem_context()

                        # Check if price action can be mentioned
                        can_mention_price = self.price_tracker.can_mention_price()
                        price_constraint = ""
                        if not can_mention_price:
                            hours_remaining = self.price_tracker.get_time_until_next_allowed()
                            price_constraint = f"\n\nIMPORTANT CONSTRAINT: DO NOT mention $PFP price action, price changes, or specific price numbers in this tweet. You already talked about price recently. Wait {hours_remaining:.1f} hours before mentioning price again. You can still mention $PFP in other contexts (culture, community, narrative, tech), just not price/numbers."

                        user_prompt = f"{user_prompt}\n\n{ecosystem_context}{price_constraint}\n\nUse this real-time data naturally in your tweet if relevant, but stay in character. CRITICAL: Your tweet MUST be under 260 characters total. Keep it SHORT - 1-2 lines max (under 100 characters preferred). Complete your thought - no trailing off mid-sentence."

                    # Add style learning from top-performing tweets
                    if engagement_tracker:
                        style_guidance = self._get_style_guidance(engagement_tracker)
                        if style_guidance:
                            user_prompt = f"{user_prompt}\n\n{style_guidance}"

                    # Add learned context from conversations
                    learned_context = self._get_learned_context(limit=3)
                    if learned_context:
                        user_prompt = f"{user_prompt}\n\n{learned_context}"

                logger.debug(f"Using content type: {template.content_type.value if not custom_prompt else 'custom'}")

                # Generate content
                content = self.claude_client.generate_content(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=100,  # Short tweets - most under 100 chars
                    temperature=0.8  # Higher temperature for creativity
                )

                if not content:
                    logger.warning(f"Failed to generate content on attempt {attempt + 1}")
                    continue

                # Clean up content
                content = content.strip()

                # Remove quotes if Claude added them
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1]
                if content.startswith("'") and content.endswith("'"):
                    content = content[1:-1]

                # Strip any emojis that slipped through
                content = self._strip_emojis(content)

                # Check if content contains "gm" and filter if already used today
                if self._contains_gm(content):
                    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                    if self.last_gm_date == today:
                        logger.warning("Rejecting tweet with 'gm' - already used today")
                        continue
                    else:
                        # This is the first gm of the day
                        logger.info(f"Allowing 'gm' - first time today ({today})")

                # Check if content is too similar to recent tweets
                if self._is_too_similar(content):
                    logger.warning("Rejecting tweet - too similar to recent content")
                    continue

                # Validate content
                is_valid, errors = self.validator.validate(content)

                if is_valid:
                    # Self-critique before accepting
                    score, feedback = self.critic.critique_tweet(content)

                    if score < 8:
                        logger.warning(f"Tweet scored {score}/10, regenerating. Feedback: {feedback[:100]}")
                        continue  # Try again

                    logger.info(f"Tweet approved with score {score}/10")
                    logger.info(f"Successfully generated valid tweet: {content[:50]}...")
                    # Track this topic for variety
                    if not custom_prompt:
                        self._track_topic(template.content_type)
                    # Update last gm date if content contains gm
                    if self._contains_gm(content):
                        self.last_gm_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                        logger.info(f"Updated last_gm_date to {self.last_gm_date}")
                    # Track price mention if content mentions price
                    if self._contains_price_action(content):
                        self.price_tracker.record_price_mention()
                        logger.info("Recorded price action mention")
                    # Track tweet for similarity checking
                    self._track_tweet(content)
                    return content
                else:
                    logger.warning(f"Generated content failed validation: {errors}")
                    # Don't sanitize - reject and regenerate instead to avoid truncation
                    # This ensures tweets are complete, not cut off mid-sentence
                    continue

            except Exception as e:
                logger.error(f"Error generating tweet: {e}", exc_info=True)

        logger.error(f"Failed to generate valid tweet after {max_attempts} attempts")
        return None

    def generate_tweet_about_specific_token(
        self,
        token_address: str,
        content_type: Optional[ContentType] = None
    ) -> Optional[str]:
        """
        Generate a tweet about a specific token.

        Args:
            token_address: Token contract address
            content_type: Type of content (defaults to TOKEN_LAUNCH)

        Returns:
            Generated tweet or None
        """
        try:
            logger.info(f"Generating tweet about token {token_address[:8]}...")

            # Fetch token data
            token_data = self.pumpfun_client.get_token_info(token_address)

            if not token_data:
                logger.warning("Could not fetch token data")
                return None

            # Build custom prompt with token data
            token_name = token_data.get('name', 'Unknown Token')
            token_symbol = token_data.get('symbol', '???')
            market_cap = token_data.get('market_cap', 'unknown')
            price_change = token_data.get('price_change_24h', 0)

            custom_prompt = f"""Tweet about this specific token on Pump.fun:
Name: {token_name}
Symbol: ${token_symbol}
Market Cap: {market_cap}
24h Change: {price_change}%

Make it Pepe-style: cheeky, smart, observant. Comment on the token naturally."""

            return self.generate_tweet(
                custom_prompt=custom_prompt,
                use_live_data=False  # Already have specific data
            )

        except Exception as e:
            logger.error(f"Error generating token-specific tweet: {e}")
            return None

    def generate_thread(
        self,
        content_type: Optional[ContentType] = None,
        topic: Optional[str] = None,
        num_tweets: int = 3,
        max_attempts: int = 3,
        use_live_data: bool = True
    ) -> Optional[List[str]]:
        """
        Generate a thread of tweets.

        Args:
            content_type: Type of content to generate
            topic: Specific topic for the thread
            num_tweets: Number of tweets in thread
            max_attempts: Maximum attempts to generate valid thread
            use_live_data: Whether to include live Pump.fun data

        Returns:
            List of tweet texts or None if failed
        """
        for attempt in range(max_attempts):
            try:
                logger.debug(f"Generating thread (attempt {attempt + 1}/{max_attempts})")

                # Select template
                template = self._select_template(content_type)

                # Build thread prompt
                base_context = ""
                if use_live_data and self._should_use_live_data(template.content_type):
                    base_context = self._build_ecosystem_context()

                if topic:
                    thread_prompt = f"Create a Twitter thread with {num_tweets} tweets about: {topic}. Each tweet should be on a separate line, numbered 1/, 2/, 3/, etc. Keep each tweet under 280 characters."
                else:
                    base_prompt = random.choice(template.user_prompts)
                    thread_prompt = f"Expand on this topic into a Twitter thread with {num_tweets} tweets: {base_prompt}. Each tweet should be on a separate line, numbered 1/, 2/, 3/, etc. Keep each tweet under 280 characters."

                if base_context:
                    thread_prompt = f"{thread_prompt}\n\n{base_context}\n\nIncorporate this live data naturally if relevant."

                # Generate thread content
                content = self.claude_client.generate_content(
                    prompt=thread_prompt,
                    system_prompt=template.system_prompt,
                    max_tokens=800,
                    temperature=0.8
                )

                if not content:
                    logger.warning(f"Failed to generate thread on attempt {attempt + 1}")
                    continue

                # Parse thread into individual tweets
                tweets = self._parse_thread(content, num_tweets)

                if not tweets or len(tweets) < num_tweets:
                    logger.warning(f"Failed to parse thread correctly")
                    continue

                # Validate all tweets
                all_valid = True
                validated_tweets = []

                for i, tweet in enumerate(tweets):
                    is_valid, errors = self.validator.validate(tweet)
                    if is_valid:
                        validated_tweets.append(tweet)
                    else:
                        # Try to sanitize
                        sanitized = self.validator.sanitize(tweet)
                        is_valid_sanitized, _ = self.validator.validate(sanitized)
                        if is_valid_sanitized:
                            validated_tweets.append(sanitized)
                        else:
                            logger.warning(f"Tweet {i + 1} in thread failed validation: {errors}")
                            all_valid = False
                            break

                if all_valid and len(validated_tweets) == num_tweets:
                    logger.info(f"Successfully generated thread with {len(validated_tweets)} tweets")
                    return validated_tweets

            except Exception as e:
                logger.error(f"Error generating thread: {e}", exc_info=True)

        logger.error(f"Failed to generate valid thread after {max_attempts} attempts")
        return None

    def _should_use_live_data(self, content_type: ContentType) -> bool:
        """
        Determine if live data should be used for this content type.

        Args:
            content_type: Type of content being generated

        Returns:
            True if live data is relevant
        """
        # Use live data for these content types
        live_data_types = [
            ContentType.TOKEN_LAUNCH,
            ContentType.MARKET_ANALYSIS,
            ContentType.ECOSYSTEM_UPDATE,
            ContentType.RAGE_BAIT,  # Hot takes on current events
            ContentType.PFP_SHILL,  # NEW: $PFP content needs live price data
            ContentType.PFP_PRICE_ACTION,  # NEW: $PFP price action needs real data
            ContentType.SUPERCYCLE_VISION,  # NEW: Future predictions need current data as baseline
        ]
        return content_type in live_data_types

    def _get_style_guidance(self, engagement_tracker) -> Optional[str]:
        """
        Get style guidance from top-performing tweets.

        Args:
            engagement_tracker: EngagementTracker instance with tweet data

        Returns:
            Formatted style guidance string or None
        """
        try:
            # Get top 3 performing tweets
            top_tweets = engagement_tracker.get_top_performing_tweets(limit=3)

            if not top_tweets or len(top_tweets) < 2:
                return None

            # Build style guidance
            guidance_parts = ["STYLE LEARNING - Your recent high-performing tweets:"]

            for i, tweet_data in enumerate(top_tweets, 1):
                score = tweet_data['score']
                text = tweet_data['text']
                metrics = tweet_data['metrics']
                likes = metrics['likes']
                retweets = metrics['retweets']
                replies = metrics['replies']

                guidance_parts.append(
                    f"{i}. (Score: {score:.0f}, {likes}❤️ {retweets}🔄 {replies}💬) \"{text}\""
                )

            guidance_parts.append(
                "\nUse similar energy, topics, and style that resonate with your audience. "
                "Learn from what works - these tweets got the most engagement."
            )

            guidance = "\n".join(guidance_parts)
            logger.info("Added style guidance from top-performing tweets")
            return guidance

        except Exception as e:
            logger.error(f"Error getting style guidance: {e}")
            return None

    def _strip_emojis(self, content: str) -> str:
        """
        Remove all emoji characters from content.

        Args:
            content: Content to strip emojis from

        Returns:
            Content with emojis removed
        """
        # Remove emojis and other special Unicode characters
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U00002600-\U000026FF"  # Miscellaneous Symbols
            "]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub('', content).strip()

    def _contains_gm(self, content: str) -> bool:
        """
        Check if content contains 'gm' (case insensitive, whole word).

        Args:
            content: Content to check

        Returns:
            True if contains 'gm'
        """
        # Match 'gm' as a whole word (not part of other words)
        pattern = r'\bgm\b'
        return bool(re.search(pattern, content, re.IGNORECASE))

    def _contains_price_action(self, content: str) -> bool:
        """
        Check if content mentions price action or specific prices.

        Args:
            content: Content to check

        Returns:
            True if contains price-related mentions
        """
        content_lower = content.lower()

        # Price keywords and patterns
        price_indicators = [
            'price', 'mcap', 'market cap', 'volume',
            '$0.', 'cent', 'dollar', 'usd',
            'up', 'down', 'pump', 'dump',
            'moon', 'ath', 'dip', 'breakout',
            'chart', 'candle', 'support', 'resistance',
            'buy', 'bought', 'sold', 'bag'
        ]

        # Check for price indicators along with $PFP mention
        has_pfp = '$pfp' in content_lower or 'pfp' in content_lower
        has_price_indicator = any(indicator in content_lower for indicator in price_indicators)

        # Also check for numerical patterns that might be prices
        has_price_pattern = bool(re.search(r'\$\d+\.?\d*[mkb]?', content_lower))

        return has_pfp and (has_price_indicator or has_price_pattern)

    def _is_too_similar(self, new_content: str) -> bool:
        """
        Check if new content is too similar to recent tweets.
        Uses word overlap and key phrase matching.

        Args:
            new_content: New tweet content to check

        Returns:
            True if too similar to recent tweets
        """
        if not self.recent_tweets:
            return False

        # Normalize content for comparison
        new_words = set(re.findall(r'\b\w+\b', new_content.lower()))

        # Extract key phrases (3+ words)
        new_phrases = set()
        words_list = new_content.lower().split()
        for i in range(len(words_list) - 2):
            phrase = ' '.join(words_list[i:i+3])
            new_phrases.add(phrase)

        for recent_tweet in self.recent_tweets:
            recent_words = set(re.findall(r'\b\w+\b', recent_tweet.lower()))

            # Calculate word overlap (excluding common words)
            common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'is', 'are', 'was', 'were'}
            meaningful_new = new_words - common_words
            meaningful_recent = recent_words - common_words

            if meaningful_new and meaningful_recent:
                overlap = len(meaningful_new & meaningful_recent) / len(meaningful_new)

                # If more than 60% word overlap, it's too similar
                if overlap > 0.6:
                    logger.warning(f"Content too similar to recent tweet ({overlap:.1%} overlap)")
                    return True

            # Check for exact phrase matches (3+ words)
            recent_phrases = set()
            recent_words_list = recent_tweet.lower().split()
            for i in range(len(recent_words_list) - 2):
                phrase = ' '.join(recent_words_list[i:i+3])
                recent_phrases.add(phrase)

            phrase_overlap = new_phrases & recent_phrases
            if phrase_overlap:
                logger.warning(f"Content contains repeated phrase: {list(phrase_overlap)[0]}")
                return True

        return False

    def _track_tweet(self, content: str) -> None:
        """
        Track a tweet in recent history for similarity checking.

        Args:
            content: Tweet content to track
        """
        self.recent_tweets.append(content)
        # Keep only last N tweets
        if len(self.recent_tweets) > self.recent_tweets_limit:
            self.recent_tweets.pop(0)
        logger.debug(f"Tracked tweet. Recent tweets count: {len(self.recent_tweets)}")

    def _track_topic(self, content_type: ContentType) -> None:
        """
        Track a topic to maintain variety.

        Args:
            content_type: Content type that was just used
        """
        self.recent_topics.append(content_type)
        # Keep only last N topics
        if len(self.recent_topics) > self.topic_history_size:
            self.recent_topics.pop(0)
        logger.debug(f"Tracked topic: {content_type.value}. Recent: {[t.value for t in self.recent_topics]}")

    def _select_template(self, content_type: Optional[ContentType] = None) -> ContentTemplate:
        """
        Select a template, either specific type or weighted random.
        Avoids recently used topics for variety.

        Args:
            content_type: Specific content type to use

        Returns:
            Selected template
        """
        if content_type:
            return self.templates.get_template_by_type(content_type)

        # Weighted random selection with topic variety
        weighted_templates = self.templates.get_weighted_templates()

        # Filter out recently used topics if we have history
        if len(self.recent_topics) >= 2:
            # Don't use topics from last 2 tweets
            recent_set = set(self.recent_topics[-2:])
            available_templates = [
                t for t in weighted_templates
                if t["template"].content_type not in recent_set
            ]

            # If we filtered out everything, just use all templates
            if not available_templates:
                available_templates = weighted_templates
                logger.debug("All topics recently used, allowing all")
            else:
                logger.debug(f"Filtered out recent topics: {[t.value for t in recent_set]}")

            weighted_templates = available_templates

        selected = random_choice_weighted(weighted_templates, weight_key="weight")
        return selected["template"]

    def _parse_thread(self, content: str, expected_count: int) -> List[str]:
        """
        Parse thread content into individual tweets.

        Args:
            content: Raw thread content
            expected_count: Expected number of tweets

        Returns:
            List of individual tweets
        """
        tweets = []

        # Try parsing numbered format (1/, 2/, etc.)
        lines = content.strip().split('\n')
        current_tweet = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line starts with number/
            if any(line.startswith(f"{i}/") or line.startswith(f"{i}.") for i in range(1, expected_count + 2)):
                if current_tweet:
                    tweet_text = ' '.join(current_tweet)
                    # Remove numbering
                    tweet_text = tweet_text.split('/', 1)[-1].strip()
                    tweet_text = tweet_text.split('.', 1)[-1].strip()
                    tweets.append(tweet_text)
                    current_tweet = []

                current_tweet.append(line)
            else:
                current_tweet.append(line)

        # Add last tweet
        if current_tweet:
            tweet_text = ' '.join(current_tweet)
            tweet_text = tweet_text.split('/', 1)[-1].strip()
            tweet_text = tweet_text.split('.', 1)[-1].strip()
            tweets.append(tweet_text)

        # If parsing failed, try splitting by newlines
        if len(tweets) < expected_count:
            tweets = [line.strip() for line in lines if line.strip()]

        return tweets[:expected_count]
