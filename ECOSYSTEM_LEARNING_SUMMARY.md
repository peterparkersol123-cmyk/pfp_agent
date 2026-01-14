# Ecosystem Learning Feature - Summary 🧠

## What Was Added

Pepe can now **learn from the real-time Solana/Pump.fun ecosystem** and talk about:

✅ **Trending coins** - Actual tokens trending right now
✅ **Recent launches** - Newly created tokens  
✅ **Rugs** - Tokens that show rug pull indicators
✅ **Current narrative** - "Dog season", "cat season", etc.
✅ **Platform stats** - Volume, token count, activity
✅ **Specific tokens** - Deep dives into any token by address

## Files Created

### 1. `src/api/pumpfun_client.py` (NEW)
**Complete Pump.fun API integration**
- Fetches trending tokens
- Gets recent launches
- Retrieves token details
- Detects rug pulls (heuristics)
- Identifies current meta/narrative
- Built-in caching (5min TTL)
- Graceful fallbacks

**Key Methods:**
- `get_trending_tokens(limit=10)`
- `get_recent_launches(limit=20)`
- `get_token_info(address)`
- `detect_rugs(hours=24)`
- `get_trending_narrative()`
- `get_context_for_content()` ← Main one

### 2. `src/content/generator.py` (UPDATED)
**Enhanced content generation with live data**

**Added:**
- `_build_ecosystem_context()` - Builds context from live data
- `_should_use_live_data()` - Determines relevance
- `generate_tweet_about_specific_token()` - Token-specific tweets
- `use_live_data` parameter - Control per tweet

**Modified:**
- `generate_tweet()` - Now accepts live data context
- `generate_thread()` - Threads can use live data too
- Constructor - Takes optional PumpFunClient

### 3. `src/api/__init__.py` (UPDATED)
Added PumpFunClient export

### 4. `LIVE_DATA_INTEGRATION.md` (NEW)
Complete documentation for the feature

## How It Works

```
┌─────────────────────────────────────────┐
│  Content Generation Request             │
└────────────┬────────────────────────────┘
             │
             ▼
    ┌────────────────────┐
    │  Content Type?     │
    └────────┬───────────┘
             │
             ▼
    Is it TOKEN_LAUNCH,
    MARKET_ANALYSIS,
    ECOSYSTEM_UPDATE, or
    RAGE_BAIT?
             │
        YES  │  NO
             │
    ┌────────▼──────────┐         ┌──────────────┐
    │ PumpFunClient     │         │ Skip live    │
    │ Fetch Live Data   │         │ data fetch   │
    └────────┬──────────┘         └──────────────┘
             │
             ▼
    Build Context:
    - Trending: BONK, DOGE
    - Recent: 3 new launches
    - Rugs: 2 detected
    - Meta: dog season
             │
             ▼
    Enrich User Prompt:
    "Tweet about launches...
    
    Current ecosystem:
    - Meta: dog season
    - Trending: BONK, DOGE
    ..."
             │
             ▼
    ┌────────────────────┐
    │ Claude generates   │
    │ with real context  │
    └────────┬───────────┘
             │
             ▼
    Result: Context-aware
    Pepe tweet!
```

## Example Output Transformation

### Before (Generic Pepe)

**Prompt:** "Tweet about new tokens launching"

**Output:** 
```
someone just launched another dog coin and somehow I'm still excited.
this is what stockholm syndrome looks like in green 🐸
```

### After (Ecosystem-Aware Pepe)

**Prompt:** "Tweet about new tokens launching"

**Fetched Context:**
```
- Meta: dog season
- Trending: BONK ($BONK), DOGE2.0 ($DOGE2)
- Recent launches: 12 in last hour
- Rugs detected: 3
```

**Output:**
```
12 launches in the last hour, 3 already rugged, and $BONK still
trending. dog season hits different when the bonding curve is
your teacher 🐸📈 #Pumpfun
```

## Content Types That Auto-Use Live Data

**Enabled (automatic):**
- `TOKEN_LAUNCH` ✅
- `MARKET_ANALYSIS` ✅
- `ECOSYSTEM_UPDATE` ✅
- `RAGE_BAIT` ✅

**Disabled (uses general knowledge):**
- `DEGEN_WISDOM`
- `CULT_LEADER`
- `PEPE_SHITPOST`
- `TRADING_TIPS`
- `COMMUNITY_HIGHLIGHT`
- `EDUCATIONAL`
- `GENERAL`

## API Endpoints Used

**Pump.fun Frontend API:**
- `/coins/trending` - Trending tokens
- `/coins` - Recent launches
- `/coins/{address}` - Token details
- `/stats` - Platform statistics

**DexScreener:**
- `/latest/dex/tokens/{address}` - DEX data

## Features

### 🔴 Real-Time Data
- Fetches live ecosystem state
- Updates every post (with caching)
- Falls back gracefully if APIs down

### 🧠 Smart Context Building
- Automatically determines relevance
- Only fetches when needed
- Formats data for Claude naturally

### 🎯 Rug Detection
Uses heuristics:
- Low liquidity (< $100)
- High concentration (> 50% top holder)
- Price dumps (> 80% down)
- Suspicious activity patterns

### 💾 Caching
- 5-minute TTL for trending/recent
- 1-minute TTL for specific tokens
- 10-minute TTL for platform stats
- Reduces API calls, improves performance

### 🛡️ Error Handling
- API timeout handling
- Graceful fallbacks
- Continues working if APIs fail
- Logs all issues for debugging

## Usage

### Automatic (Recommended)

```python
# Just use the generator normally
generator = ContentGenerator()  # Auto-initializes with live data

# These automatically use live data:
tweet = generator.generate_tweet(content_type=ContentType.TOKEN_LAUNCH)
tweet = generator.generate_tweet(content_type=ContentType.MARKET_ANALYSIS)
```

### Manual Control

```python
# Disable live data for specific tweet
tweet = generator.generate_tweet(
    content_type=ContentType.TOKEN_LAUNCH,
    use_live_data=False
)

# Tweet about specific token
tweet = generator.generate_tweet_about_specific_token(
    token_address="SomeTokenAddress123"
)
```

### Check What Data is Fetched

```python
from src.api.pumpfun_client import PumpFunClient

client = PumpFunClient()
context = client.get_context_for_content()

print(context['trending_tokens'])
print(context['narrative'])
print(context['suspicious_activity'])
```

## Performance

**Latency Impact:**
- First call: +1-3s (fetching data)
- Cached calls: +0.1-0.5s (cache hit)
- API failure: +0s (immediate fallback)

**Memory:**
- Cache: ~1-5MB
- Minimal footprint

**API Requests:**
- ~4-6 requests per context build
- Cached for 5 minutes
- ~12-72 requests/hour (depending on post frequency)

## Configuration

None required! Works out of the box.

**Optional tweaks in code:**
```python
# Adjust cache TTL
client.cache_ttl = 600  # 10 minutes

# Adjust which content types use live data
# In generator.py, modify _should_use_live_data()
```

## What Pepe Knows Now

Before today, Pepe was smart but generic.

**Now Pepe knows:**
- What's trending on Pump.fun THIS SECOND
- Which tokens just launched THIS HOUR
- What rugged YESTERDAY
- If it's dog season, cat season, or chaos season
- Real volume numbers, real activity

**Result**: 
- ❌ Generic: "New tokens are launching!"
- ✅ Specific: "$BONK trending with 3 rugs in 24h"

## Testing

```bash
# Run the test suite (will test PumpFun integration)
python test_agent.py

# Check logs for data fetching
tail -f logs/agent.log | grep "ecosystem"

# Manual test
python -c "
from src.api.pumpfun_client import PumpFunClient
client = PumpFunClient()
print(client.get_context_for_content())
"
```

## Maintenance

**If APIs change:**
1. Check `pumpfun_client.py` line 14-15 (base URLs)
2. Update endpoint paths as needed
3. Adjust response parsing if format changes

**If you want different data:**
- Extend `PumpFunClient` class
- Add new methods for your data source
- Update `get_context_for_content()` to include it

## Future Enhancements

Could add:
- On-chain Solana data
- Whale wallet tracking
- Twitter sentiment
- Telegram activity
- Historical trends
- WebSocket live feeds

## Summary

**Added:** Full real-time Pump.fun ecosystem integration

**Impact:** Pepe now posts about ACTUAL events, not generic content

**Effort:** Zero - works automatically for relevant content types

**Maintenance:** Low - graceful fallbacks if APIs change

**Result:** Context-aware AI agent that knows what's happening RIGHT NOW in the ecosystem

*the frog is now omniscient anon 🐸👁️*
