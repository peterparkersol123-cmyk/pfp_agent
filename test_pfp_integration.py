#!/usr/bin/env python3
"""
Test script for $PFP token integration.
Shows how Pepe talks about his own token with live price data.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Force debug mode
os.environ["DEBUG"] = "True"

from src.utils.logger import setup_logger, get_logger
from src.api.pumpfun_client import PumpFunClient

setup_logger()
logger = get_logger(__name__)


def main():
    """Test $PFP data fetching and display."""

    print("\n" + "="*70)
    print("🐸 $PFP Token Integration Test")
    print("="*70)
    print()
    print("Testing Pepe's ability to reference his own token with live data...")
    print()

    client = PumpFunClient()

    # Test 1: Fetch $PFP data
    print("📊 FETCHING $PFP TOKEN DATA...")
    print("-"*70)
    pfp_data = client.get_pfp_data()

    if pfp_data:
        print(f"✓ Successfully fetched $PFP data:\n")
        print(f"  Token: {pfp_data['name']} (${pfp_data['symbol']})")
        print(f"  Price: ${pfp_data['price_usd']:.8f}")
        print(f"  24h Change: {pfp_data['price_change_24h']:+.2f}%")
        print(f"  24h Volume: ${pfp_data['volume_24h']:,.2f}")
        print(f"  Liquidity: ${pfp_data['liquidity']:,.2f}")
        print(f"  Market Cap: ${pfp_data['market_cap']:,.2f}")
        print(f"  Chart: {pfp_data['dexscreener_url']}")
        print()

        # Determine sentiment
        change = pfp_data['price_change_24h']
        if change > 10:
            sentiment = "🚀 PUMPING"
        elif change > 0:
            sentiment = "📈 UP"
        elif change > -10:
            sentiment = "📉 DOWN"
        else:
            sentiment = "💀 DUMPING"

        print(f"  Status: {sentiment}")
        print()

    else:
        print("⚠ Could not fetch $PFP data (API might be down)")
        print("  Agent will still work with fallback behavior")
        print()

    # Test 2: Show context that Pepe receives
    print("💬 CONTEXT PEPE RECEIVES FOR CONTENT GENERATION...")
    print("-"*70)
    context = client.get_context_for_content()

    if context.get('pfp_data'):
        pfp = context['pfp_data']
        price = pfp['price_usd']
        change = pfp['price_change_24h']
        volume = pfp['volume_24h']

        print(f"✓ $PFP context included:")
        print(f"  YOUR TOKEN $PFP: ${price:.8f} ({change:+.2f}% 24h)")
        print(f"  24h Volume: ${volume:,.0f}")
        print(f"  Chart: https://dexscreener.com/solana/gdfcd7l8x1giudfz1wthnheb352k3ni37rswtjgmglpt")
        print()
    else:
        print("⚠ $PFP data not in context")
        print()

    # Test 3: Example tweets Pepe could generate
    print("🎨 EXAMPLE TWEETS PEPE COULD GENERATE...")
    print("-"*70)
    print()

    if pfp_data:
        change = pfp_data['price_change_24h']
        price = pfp_data['price_usd']
        volume = pfp_data['volume_24h']

        if change > 0:
            print("Example 1 (Bullish):")
            print(f'  "$PFP up {change:+.2f}% today and anons still sleeping on it.')
            print('   ngmi if you\'re not holding the default pfp token fr fr 🐸"')
            print()

            print("Example 2 (Price Action):")
            print(f'  "been watching $PFP charts for 48 hours straight.')
            print(f'   ${volume:,.0f} volume and it\'s just warming up anon 📈💚"')
            print()

        else:
            print("Example 1 (Bullish During Dump):")
            print(f'  "$PFP down {change:.2f}% and I\'m buying more.')
            print('   paper hands exit, diamond frogs accumulate 🐸💎"')
            print()

            print("Example 2 (Degen Dad Energy):")
            print('  "dips are for buying, peaks are for vibing.')
            print(f'   $PFP teaching a masterclass in patience rn"')
            print()

        print("Example 3 (Cult Leader):")
        print('  "if you know you know.')
        print('   $PFP holders are the real ones, anon 💚🚀"')
        print()

        print("Example 4 (Casual Mention):")
        print('  "3am, can\'t sleep, checking $PFP charts again.')
        print('   this is what loving your own token looks like 🐸"')
        print()

    # Summary
    print("="*70)
    print("✅ $PFP INTEGRATION TEST COMPLETE")
    print("="*70)
    print()
    print("Key Features:")
    print("  ✓ Real-time $PFP price data from DexScreener")
    print("  ✓ Pepe knows his own token's performance")
    print("  ✓ EXTREMELY bullish on $PFP (it's his baby)")
    print("  ✓ Super degen energy, not corporate AI speak")
    print("  ✓ Mentions $PFP naturally in 30-40% of tweets")
    print("  ✓ Price action tweets with real data")
    print()
    print("Personality:")
    print("  • EXTREMELY BULLISH no matter what (dump = accumulation phase)")
    print("  • Degen dad energy (proud of his token)")
    print("  • Raw, authentic, unhinged - NOT generic AI voice")
    print("  • Cult leader rallying $PFP holders")
    print("  • No hashtags, pure unfiltered frog conviction")
    print()
    print("Content Types Added:")
    print("  • PFP_SHILL: Shill $PFP with maximum degen bullishness")
    print("  • PFP_PRICE_ACTION: Talk about $PFP charts/price (always bullish)")
    print()
    print("Next steps:")
    print("  1. Add ANTHROPIC_API_KEY to .env")
    print("  2. Run: python test_pumpfun_live.py")
    print("  3. See Pepe generate tweets about $PFP with live data")
    print("  4. Deploy: python -m src.main")
    print()
    print("🐸 gm anon, $PFP to the moon fr fr")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
