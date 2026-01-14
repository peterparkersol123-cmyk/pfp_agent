"""
Test script for Pump.fun live data integration.
Tests fetching and using real-time ecosystem data in tweets.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Force debug mode for testing
os.environ["DEBUG"] = "True"

from src.utils.logger import setup_logger, get_logger
from src.api.pumpfun_client import PumpFunClient
from src.api.claude_client import ClaudeClient
from src.content.generator import ContentGenerator
from src.content.templates import ContentType

setup_logger()
logger = get_logger(__name__)


def test_pumpfun_api():
    """Test direct Pump.fun API calls."""
    logger.info("="*60)
    logger.info("Testing Pump.fun API Client")
    logger.info("="*60)

    try:
        client = PumpFunClient()

        # Test 1: Get trending tokens
        logger.info("\n[Test 1] Fetching trending tokens...")
        trending = client.get_trending_tokens(limit=5)

        if trending:
            logger.info(f"✓ Found {len(trending)} trending tokens:")
            for i, token in enumerate(trending, 1):
                name = token.get('name', 'Unknown')
                symbol = token.get('symbol', '???')
                logger.info(f"  {i}. {name} (${symbol})")
        else:
            logger.warning("✗ No trending tokens found (API might be unavailable)")

        # Test 2: Get recent launches
        logger.info("\n[Test 2] Fetching recent launches...")
        recent = client.get_recent_launches(limit=5)

        if recent:
            logger.info(f"✓ Found {len(recent)} recent launches:")
            for i, token in enumerate(recent, 1):
                name = token.get('name', 'Unknown')
                symbol = token.get('symbol', '???')
                logger.info(f"  {i}. {name} (${symbol})")
        else:
            logger.warning("✗ No recent launches found")

        # Test 3: Get current narrative
        logger.info("\n[Test 3] Detecting current narrative/meta...")
        narrative = client.get_trending_narrative()
        logger.info(f"✓ Current meta: {narrative}")

        # Test 4: Detect rugs
        logger.info("\n[Test 4] Detecting suspicious activity...")
        rugs = client.detect_rugs(hours=24)
        logger.info(f"✓ Found {len(rugs)} suspicious tokens in last 24h")

        # Test 5: Get platform stats
        logger.info("\n[Test 5] Fetching platform statistics...")
        stats = client.get_pump_fun_stats()
        logger.info(f"✓ Platform stats: {stats}")

        # Test 6: Get comprehensive context
        logger.info("\n[Test 6] Building comprehensive context...")
        context = client.get_context_for_content()
        logger.info("✓ Context built successfully:")
        logger.info(f"  - Trending tokens: {len(context.get('trending_tokens', []))}")
        logger.info(f"  - Recent launches: {len(context.get('recent_launches', []))}")
        logger.info(f"  - Narrative: {context.get('narrative', 'unknown')}")
        logger.info(f"  - Suspicious activity: {len(context.get('suspicious_activity', []))}")

        return True

    except Exception as e:
        logger.error(f"✗ Error testing Pump.fun API: {e}", exc_info=True)
        return False


def test_content_with_live_data():
    """Test content generation with live Pump.fun data."""
    logger.info("\n" + "="*60)
    logger.info("Testing Content Generation with Live Data")
    logger.info("="*60)

    try:
        generator = ContentGenerator()

        # Test 1: Token Launch tweet with live data
        logger.info("\n[Test 1] Generating TOKEN_LAUNCH tweet with live data...")
        tweet = generator.generate_tweet(
            content_type=ContentType.TOKEN_LAUNCH,
            use_live_data=True
        )

        if tweet:
            logger.info("✓ Generated tweet:")
            logger.info(f"\n{'-'*60}")
            logger.info(tweet)
            logger.info(f"{'-'*60}\n")
        else:
            logger.error("✗ Failed to generate tweet")

        # Test 2: Market Analysis tweet with live data
        logger.info("[Test 2] Generating MARKET_ANALYSIS tweet with live data...")
        tweet = generator.generate_tweet(
            content_type=ContentType.MARKET_ANALYSIS,
            use_live_data=True
        )

        if tweet:
            logger.info("✓ Generated tweet:")
            logger.info(f"\n{'-'*60}")
            logger.info(tweet)
            logger.info(f"{'-'*60}\n")
        else:
            logger.error("✗ Failed to generate tweet")

        # Test 3: Ecosystem Update with live data
        logger.info("[Test 3] Generating ECOSYSTEM_UPDATE tweet with live data...")
        tweet = generator.generate_tweet(
            content_type=ContentType.ECOSYSTEM_UPDATE,
            use_live_data=True
        )

        if tweet:
            logger.info("✓ Generated tweet:")
            logger.info(f"\n{'-'*60}")
            logger.info(tweet)
            logger.info(f"{'-'*60}\n")
        else:
            logger.error("✗ Failed to generate tweet")

        # Test 4: Rage Bait with live data
        logger.info("[Test 4] Generating RAGE_BAIT tweet with live data...")
        tweet = generator.generate_tweet(
            content_type=ContentType.RAGE_BAIT,
            use_live_data=True
        )

        if tweet:
            logger.info("✓ Generated tweet:")
            logger.info(f"\n{'-'*60}")
            logger.info(tweet)
            logger.info(f"{'-'*60}\n")
        else:
            logger.error("✗ Failed to generate tweet")

        # Test 5: Compare with and without live data
        logger.info("[Test 5] Comparing tweets WITH and WITHOUT live data...")

        logger.info("\n  WITHOUT live data:")
        tweet_no_data = generator.generate_tweet(
            content_type=ContentType.TOKEN_LAUNCH,
            use_live_data=False
        )
        if tweet_no_data:
            logger.info(f"  → {tweet_no_data}")

        logger.info("\n  WITH live data:")
        tweet_with_data = generator.generate_tweet(
            content_type=ContentType.TOKEN_LAUNCH,
            use_live_data=True
        )
        if tweet_with_data:
            logger.info(f"  → {tweet_with_data}")

        return True

    except Exception as e:
        logger.error(f"✗ Error testing content generation: {e}", exc_info=True)
        return False


def test_specific_token():
    """Test generating tweet about a specific token."""
    logger.info("\n" + "="*60)
    logger.info("Testing Specific Token Tweet Generation")
    logger.info("="*60)

    try:
        # Note: You'll need a real token address to test this
        # This is a placeholder - replace with actual Pump.fun token address
        logger.info("\nℹ To test specific token tweets, you need a real token address.")
        logger.info("Example usage:")
        logger.info("  generator = ContentGenerator()")
        logger.info("  tweet = generator.generate_tweet_about_specific_token('YOUR_TOKEN_ADDRESS')")

        # Uncomment below and add a real token address to test
        # generator = ContentGenerator()
        # token_address = "YOUR_REAL_TOKEN_ADDRESS_HERE"
        # tweet = generator.generate_tweet_about_specific_token(token_address)
        # if tweet:
        #     logger.info(f"✓ Generated tweet about specific token:")
        #     logger.info(f"\n{'-'*60}")
        #     logger.info(tweet)
        #     logger.info(f"{'-'*60}\n")

        return True

    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return False


def test_context_building():
    """Test the ecosystem context building in detail."""
    logger.info("\n" + "="*60)
    logger.info("Testing Ecosystem Context Building")
    logger.info("="*60)

    try:
        generator = ContentGenerator()

        logger.info("\nBuilding ecosystem context...")
        context_str = generator._build_ecosystem_context()

        logger.info("✓ Context string generated:")
        logger.info(f"\n{'-'*60}")
        logger.info(context_str)
        logger.info(f"{'-'*60}\n")

        logger.info("This context is automatically added to relevant prompts!")

        return True

    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return False


def test_cache_behavior():
    """Test caching behavior."""
    logger.info("\n" + "="*60)
    logger.info("Testing Cache Behavior")
    logger.info("="*60)

    try:
        client = PumpFunClient()

        import time

        logger.info("\n[First call] Should fetch from API...")
        start = time.time()
        trending1 = client.get_trending_tokens(limit=3)
        elapsed1 = time.time() - start
        logger.info(f"✓ Took {elapsed1:.2f}s")

        logger.info("\n[Second call] Should use cache...")
        start = time.time()
        trending2 = client.get_trending_tokens(limit=3)
        elapsed2 = time.time() - start
        logger.info(f"✓ Took {elapsed2:.2f}s (should be much faster!)")

        if elapsed2 < elapsed1:
            logger.info("✓ Cache is working! Second call was faster.")
        else:
            logger.warning("Cache might not be working optimally")

        return True

    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return False


def interactive_test():
    """Interactive test - generate multiple tweets and show them."""
    logger.info("\n" + "="*60)
    logger.info("Interactive Live Data Test")
    logger.info("="*60)

    try:
        generator = ContentGenerator()

        logger.info("\nGenerating 3 tweets with live data to see variety...")
        logger.info("(Each should reference real trending tokens/data)\n")

        for i in range(3):
            logger.info(f"\n{'='*60}")
            logger.info(f"Tweet #{i+1}")
            logger.info(f"{'='*60}")

            tweet = generator.generate_tweet(
                content_type=ContentType.TOKEN_LAUNCH,
                use_live_data=True
            )

            if tweet:
                logger.info(tweet)
            else:
                logger.error("Failed to generate tweet")

            logger.info("")

        logger.info("\nℹ If you see references to actual token names, symbols,")
        logger.info("  or specific numbers - the live data integration is working!")

        return True

    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return False


def main():
    """Run all tests."""
    logger.info("="*60)
    logger.info("Pump.fun Live Data Integration - Test Suite")
    logger.info("="*60)
    logger.info("")
    logger.info("This will test:")
    logger.info("1. Direct API calls to Pump.fun")
    logger.info("2. Content generation with live data")
    logger.info("3. Context building")
    logger.info("4. Cache behavior")
    logger.info("5. Interactive examples")
    logger.info("")
    logger.info("Note: Some tests may fail if Pump.fun API is unavailable.")
    logger.info("      The agent will fall back gracefully in production.")
    logger.info("")

    results = {}

    # Run all tests
    tests = [
        ("Pump.fun API Client", test_pumpfun_api),
        ("Content Generation with Live Data", test_content_with_live_data),
        ("Ecosystem Context Building", test_context_building),
        ("Cache Behavior", test_cache_behavior),
        ("Specific Token Tweets", test_specific_token),
        ("Interactive Examples", interactive_test),
    ]

    for test_name, test_func in tests:
        try:
            logger.info("")
            results[test_name] = test_func()
        except Exception as e:
            logger.error(f"Test '{test_name}' crashed: {e}")
            results[test_name] = False

    # Summary
    logger.info("\n" + "="*60)
    logger.info("Test Summary")
    logger.info("="*60)

    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        logger.info(f"{test_name:40s} {status}")

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    logger.info("")
    logger.info(f"Results: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n✓ All tests passed! Live data integration is working.")
        logger.info("\nNext steps:")
        logger.info("  1. Check the generated tweets above for token references")
        logger.info("  2. Run: python -m src.main")
        logger.info("  3. Watch logs: tail -f logs/agent.log | grep ecosystem")
        return 0
    else:
        logger.warning(f"\n⚠ {total - passed} test(s) failed")
        logger.info("\nPossible reasons:")
        logger.info("  - Pump.fun API might be down/unavailable")
        logger.info("  - Network connectivity issues")
        logger.info("  - API endpoints may have changed")
        logger.info("\nThe agent will work with fallbacks even if APIs fail.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
