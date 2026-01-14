#!/usr/bin/env python3
"""
Test script to generate tweets using ALL content templates.
This will show you examples from every content type Pepe can generate.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.utils.logger import setup_logger, get_logger
from src.content.generator import ContentGenerator
from src.content.templates import ContentType

setup_logger()
logger = get_logger(__name__)


def main():
    """Test all content templates."""

    print("\n" + "="*70)
    print("Testing ALL Content Templates")
    print("="*70)
    print()

    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not found in .env file")
        print()
        print("Please add your API key to .env:")
        print("ANTHROPIC_API_KEY=your_key_here")
        print()
        return 1

    generator = ContentGenerator()

    # All content types to test
    content_types = [
        ContentType.TOKEN_LAUNCH,
        ContentType.MARKET_ANALYSIS,
        ContentType.TRADING_TIPS,
        ContentType.ECOSYSTEM_UPDATE,
        ContentType.COMMUNITY_HIGHLIGHT,
        ContentType.EDUCATIONAL,
        ContentType.GENERAL,
        ContentType.DEGEN_WISDOM,
        ContentType.RAGE_BAIT,
        ContentType.CULT_LEADER,
        ContentType.PEPE_SHITPOST,
        ContentType.PFP_SHILL,
        ContentType.PFP_PRICE_ACTION,
        ContentType.SUPERCYCLE_VISION,
    ]

    print(f"Generating {len(content_types)} tweets (one for each content type)...")
    print()

    results = []
    failed = []

    for i, content_type in enumerate(content_types, 1):
        print(f"[{i}/{len(content_types)}] Generating {content_type.value}...")

        try:
            tweet = generator.generate_tweet(
                content_type=content_type,
                use_live_data=True
            )

            if tweet:
                results.append({
                    'type': content_type.value,
                    'tweet': tweet
                })
                print(f"    ✓ Success")
            else:
                failed.append(content_type.value)
                print(f"    ✗ Failed to generate")

        except Exception as e:
            failed.append(content_type.value)
            print(f"    ✗ Error: {e}")

        print()

    # Display results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    print()

    if results:
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['type'].upper().replace('_', ' ')}")
            print("-" * 70)
            print(result['tweet'])
            print()
            print()

    # Summary
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print()
    print(f"Total templates: {len(content_types)}")
    print(f"Successfully generated: {len(results)}")
    print(f"Failed: {len(failed)}")
    print()

    if failed:
        print("Failed content types:")
        for f in failed:
            print(f"  - {f}")
        print()

    # Check for common issues
    print("="*70)
    print("VALIDATION CHECKS")
    print("="*70)
    print()

    emoji_count = 0
    hashtag_count = 0
    too_long = 0

    for result in results:
        tweet = result['tweet']

        # Check for emojis
        if any(ord(char) > 127 for char in tweet):
            emoji_count += 1
            print(f"⚠ EMOJI DETECTED in {result['type']}: {tweet[:50]}...")

        # Check for hashtags
        if '#' in tweet:
            hashtag_count += 1
            print(f"⚠ HASHTAG DETECTED in {result['type']}: {tweet[:50]}...")

        # Check length
        if len(tweet) > 280:
            too_long += 1
            print(f"⚠ TOO LONG ({len(tweet)} chars) in {result['type']}: {tweet[:50]}...")

    print()
    if emoji_count == 0 and hashtag_count == 0 and too_long == 0:
        print("✓ All tweets passed validation!")
        print("  - No emojis detected")
        print("  - No hashtags detected")
        print("  - All under 280 characters")
    else:
        print("Validation issues:")
        if emoji_count > 0:
            print(f"  - {emoji_count} tweets with emojis")
        if hashtag_count > 0:
            print(f"  - {hashtag_count} tweets with hashtags")
        if too_long > 0:
            print(f"  - {too_long} tweets over 280 characters")

    print()
    print("="*70)
    print()

    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
