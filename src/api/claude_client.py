"""
Claude API client for content generation.
Handles communication with Anthropic's Claude API.

Cost controls:
- System prompts are sent with cache_control so repeated calls within the
  5-minute cache window pay ~10% of normal input cost.
- Callers can pass use_small_model=True to route low-stakes calls
  (critique, insight extraction) to the cheaper Haiku model.
"""

import time
from typing import Optional, List, Dict, Any
from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError
from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.helpers import calculate_exponential_backoff

logger = get_logger(__name__)


class ClaudeClient:
    """Client for interacting with Claude API."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Claude client.

        Args:
            api_key: Anthropic API key (uses settings if not provided)
        """
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.client = Anthropic(api_key=self.api_key)
        self.model = settings.CLAUDE_MODEL
        self.small_model = settings.CLAUDE_SMALL_MODEL
        self.max_tokens = settings.CLAUDE_MAX_TOKENS
        self.temperature = settings.CLAUDE_TEMPERATURE

        logger.info(f"Initialized Claude client (main: {self.model}, small: {self.small_model})")

    def generate_content(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        max_retries: int = 5,
        use_small_model: bool = False
    ) -> Optional[str]:
        """
        Generate content using Claude API.

        Args:
            prompt: User prompt
            system_prompt: System prompt for context
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
            max_retries: Maximum number of retry attempts
            use_small_model: Route to the cheaper Haiku model (for critique,
                insight extraction, and other low-stakes internal calls)

        Returns:
            Generated content or None if failed
        """
        max_tokens = max_tokens or self.max_tokens
        temperature = temperature or self.temperature
        model = self.small_model if use_small_model else self.model

        for attempt in range(max_retries):
            try:
                logger.debug(f"Generating content (attempt {attempt + 1}/{max_retries}, model: {model})")

                messages = [{"role": "user", "content": prompt}]

                # Build API call parameters
                api_params = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": messages
                }

                if system_prompt:
                    # cache_control: repeated calls with the same system prompt
                    # within 5 min hit the prompt cache (~90% input cost saving).
                    # Reply bursts and regeneration loops benefit the most.
                    api_params["system"] = [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]

                # Make API call
                response = self.client.messages.create(**api_params)

                # Extract content
                if response.content and len(response.content) > 0:
                    content = response.content[0].text
                    self._log_usage(response)
                    logger.info(f"Successfully generated content ({len(content)} characters)")
                    return content
                else:
                    logger.warning("Received empty response from Claude API")
                    return None

            except RateLimitError as e:
                logger.warning(f"Rate limit hit: {e}")
                if attempt < max_retries - 1:
                    delay = calculate_exponential_backoff(attempt, base_delay=5.0)
                    logger.info(f"Waiting {delay:.1f}s before retry...")
                    time.sleep(delay)
                else:
                    logger.error("Max retries reached for rate limit")
                    return None

            except APIConnectionError as e:
                logger.error(f"Connection error: {e}")
                if attempt < max_retries - 1:
                    delay = calculate_exponential_backoff(attempt)
                    logger.info(f"Waiting {delay:.1f}s before retry...")
                    time.sleep(delay)
                else:
                    logger.error("Max retries reached for connection error")
                    return None

            except APIError as e:
                logger.error(f"API error: {e}")
                # Don't retry on client errors (4xx), except 429 (rate limit)
                if hasattr(e, 'status_code') and 400 <= e.status_code < 500 and e.status_code != 429:
                    logger.error("Client error - not retrying")
                    return None
                if attempt < max_retries - 1:
                    # Longer backoff for overloaded errors (529)
                    base_delay = 10.0 if (hasattr(e, 'status_code') and e.status_code == 529) else 2.0
                    delay = calculate_exponential_backoff(attempt, base_delay=base_delay)
                    logger.info(f"Waiting {delay:.1f}s before retry...")
                    time.sleep(delay)
                else:
                    logger.error("Max retries reached for API error")
                    return None

            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                return None

        return None

    def _log_usage(self, response) -> None:
        """
        Log token usage including cache activity. If cache_read stays 0 across
        a retry/reply burst, the prompt cache is silently missing (e.g. system
        prompt below the model's minimum cacheable prefix) and we're paying
        full input price on every call.
        """
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
            logger.info(
                f"Token usage: input={usage.input_tokens} output={usage.output_tokens} "
                f"cache_read={cache_read} cache_write={cache_write}"
            )
        except Exception:
            pass  # Usage logging must never break generation

    def generate_content_streaming(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Optional[str]:
        """
        Generate content using Claude API with streaming.

        Args:
            prompt: User prompt
            system_prompt: System prompt for context
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)

        Returns:
            Generated content or None if failed
        """
        max_tokens = max_tokens or self.max_tokens
        temperature = temperature or self.temperature

        try:
            logger.debug("Generating content with streaming")

            messages = [{"role": "user", "content": prompt}]

            # Build API call parameters
            api_params = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
                "stream": True
            }

            if system_prompt:
                api_params["system"] = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]

            # Make streaming API call
            content_chunks = []
            with self.client.messages.stream(**api_params) as stream:
                for text in stream.text_stream:
                    content_chunks.append(text)

            content = "".join(content_chunks)
            logger.info(f"Successfully generated content with streaming ({len(content)} characters)")
            return content

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            # Fallback to non-streaming
            logger.info("Falling back to non-streaming generation")
            return self.generate_content(prompt, system_prompt, max_tokens, temperature)

    def test_connection(self) -> bool:
        """
        Test connection to Claude API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info("Testing Claude API connection...")
            response = self.generate_content(
                prompt="Say 'Hello' in one word.",
                max_tokens=10,
                temperature=0,
                use_small_model=True
            )
            if response:
                logger.info("Claude API connection successful")
                return True
            else:
                logger.error("Claude API connection failed - empty response")
                return False
        except Exception as e:
            logger.error(f"Claude API connection test failed: {e}")
            return False
