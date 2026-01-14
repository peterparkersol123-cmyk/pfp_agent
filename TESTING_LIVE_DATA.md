# Testing Live Pump.fun Data Integration

## Quick Test (1 minute)

```bash
# Run the specialized test suite
python test_pumpfun_live.py
```

This will:
1. ✅ Test Pump.fun API connectivity
2. ✅ Fetch trending tokens from Pump.fun
3. ✅ Generate tweets that mention actual tokens
4. ✅ Show you the difference with/without live data
5. ✅ Demonstrate cache behavior

## What You'll See

### Successful Output Example

```
[Test 1] Fetching trending tokens...
✓ Found 5 trending tokens:
  1. BONK ($BONK)
  2. DOGE2.0 ($DOGE2)
  3. PEPE2024 ($PEPE)
  4. WOJAK ($WOJ)
  5. SHIB2 ($SHIB2)

[Test 2] Generating TOKEN_LAUNCH tweet with live data...
✓ Generated tweet:
------------------------------------------------------------
12 launches in the last hour and $BONK still trending.
dog season hits different when the bonding curve is your
teacher 🐸
------------------------------------------------------------
```

**Key indicator**: If you see actual token names/symbols (like $BONK, $DOGE2), the integration is working!

## Manual Testing

### Test 1: Fetch Trending Tokens Directly

```python
from src.api.pumpfun_client import PumpFunClient

client = PumpFunClient()

# Get trending tokens
trending = client.get_trending_tokens(limit=10)
for token in trending:
    print(f"{token.get('name')} (${token.get('symbol')})")
```

### Test 2: Get Current Ecosystem Context

```python
from src.api.pumpfun_client import PumpFunClient

client = PumpFunClient()
context = client.get_context_for_content()

print("Trending:", context['trending_tokens'])
print("Narrative:", context['narrative'])
print("Recent launches:", len(context['recent_launches']))
print("Rugs detected:", len(context['suspicious_activity']))
```

### Test 3: Generate Tweet With Live Data

```python
from src.content.generator import ContentGenerator
from src.content.templates import ContentType

generator = ContentGenerator()

# This will automatically use live data
tweet = generator.generate_tweet(content_type=ContentType.TOKEN_LAUNCH)
print(tweet)
```

### Test 4: Compare With/Without Live Data

```python
from src.content.generator import ContentGenerator
from src.content.templates import ContentType

generator = ContentGenerator()

# Without live data (generic)
tweet1 = generator.generate_tweet(
    content_type=ContentType.TOKEN_LAUNCH,
    use_live_data=False
)
print("Generic:", tweet1)

# With live data (specific)
tweet2 = generator.generate_tweet(
    content_type=ContentType.TOKEN_LAUNCH,
    use_live_data=True
)
print("Live data:", tweet2)
```

### Test 5: Tweet About Specific Token

```python
from src.content.generator import ContentGenerator

generator = ContentGenerator()

# Replace with actual token address from Pump.fun
token_address = "YOUR_TOKEN_ADDRESS_HERE"
tweet = generator.generate_tweet_about_specific_token(token_address)
print(tweet)
```

## Checking Logs

```bash
# Watch for ecosystem data fetching in real-time
tail -f logs/agent.log | grep "ecosystem"

# You should see lines like:
# "Fetching ecosystem data for context"
# "Built ecosystem context"
# "Successfully generated valid tweet"
```

## What to Look For

### ✅ Working Correctly

**Signs:**
- Tweets mention actual token names ($BONK, $DOGE, etc.)
- References to specific numbers (12 launches, 3 rugs, etc.)
- Current meta mentions (dog season, cat season)
- Real platform stats

**Example working tweet:**
```
"3 rugs in the last 24h, $BONK still trending, and
someone just launched $PEPE2024. the bonding curve
doesn't discriminate anon 📈"
```

### ❌ Not Working (Fallback Mode)

**Signs:**
- Generic content without specific token names
- No numbers or stats
- API errors in logs

**Example fallback tweet:**
```
"another dog coin just launched and somehow I'm still excited.
this is what stockholm syndrome looks like in green 🐸"
```

**Note:** Fallback is EXPECTED if Pump.fun API is down. The agent still works!

## Testing in Production

### Run Agent and Watch

```bash
# Terminal 1: Run the agent
python -m src.main

# Terminal 2: Watch logs
tail -f logs/agent.log
```

Look for these log entries:
```
"Fetching ecosystem data for context"
"Found X trending tokens"
"Detected Y suspicious tokens"
"Current meta: dog season"
"Built ecosystem context"
"Generated tweet: [actual token references]"
```

## API Endpoints Being Used

The test will hit these endpoints:

**Pump.fun:**
- `https://frontend-api.pump.fun/coins/trending`
- `https://frontend-api.pump.fun/coins`
- `https://frontend-api.pump.fun/stats`

**DexScreener:**
- `https://api.dexscreener.com/latest/dex/search?q=pump.fun`

## Troubleshooting

### "No trending tokens found"

**Possible causes:**
1. Pump.fun API is down
2. API endpoints changed
3. Network/firewall issues
4. Rate limiting

**Solution:**
- Agent will use fallback mode automatically
- Check if you can access the URLs in browser
- Wait and retry (might be temporary outage)

### Tweets don't reference specific tokens

**Check:**
1. Is the content type in the auto-enabled list?
   - TOKEN_LAUNCH ✅
   - MARKET_ANALYSIS ✅
   - ECOSYSTEM_UPDATE ✅
   - RAGE_BAIT ✅

2. Is `use_live_data=True`?

3. Check logs for "Fetching ecosystem data"

4. Verify API responses:
   ```python
   from src.api.pumpfun_client import PumpFunClient
   client = PumpFunClient()
   print(client.get_trending_tokens(limit=3))
   ```

### Cache is stale

**Solution:**
```python
# Clear cache by restarting
# Or manually clear:
from src.api.pumpfun_client import PumpFunClient
client = PumpFunClient()
client.cache.clear()
```

### API timeout errors

**Increase timeout in code:**
```python
# In pumpfun_client.py, line ~22
response = self.session.get(url, timeout=30)  # Increase from 10
```

## Performance Testing

### Test Cache Speed

```python
from src.api.pumpfun_client import PumpFunClient
import time

client = PumpFunClient()

# First call (API)
start = time.time()
client.get_trending_tokens()
print(f"API call: {time.time() - start:.2f}s")

# Second call (cache)
start = time.time()
client.get_trending_tokens()
print(f"Cached call: {time.time() - start:.2f}s")
```

Expected:
- First call: 1-3 seconds
- Cached call: 0.01-0.1 seconds

## Advanced: Mock Data Testing

If APIs are down, you can mock data:

```python
from src.api.pumpfun_client import PumpFunClient

class MockPumpFunClient(PumpFunClient):
    def get_trending_tokens(self, limit=10):
        return [
            {'name': 'BONK', 'symbol': 'BONK'},
            {'name': 'DOGE2.0', 'symbol': 'DOGE2'},
        ]

    def get_trending_narrative(self):
        return "dog season"

# Use in tests
from src.content.generator import ContentGenerator
generator = ContentGenerator(pumpfun_client=MockPumpFunClient())
```

## Expected Test Results

### All Tests Pass ✅

```
Results: 6/6 tests passed

✓ All tests passed! Live data integration is working.

Next steps:
  1. Check the generated tweets above for token references
  2. Run: python -m src.main
  3. Watch logs: tail -f logs/agent.log | grep ecosystem
```

### Some Tests Fail ⚠️

```
Results: 3/6 tests passed

⚠ 3 test(s) failed

Possible reasons:
  - Pump.fun API might be down/unavailable
  - Network connectivity issues
  - API endpoints may have changed

The agent will work with fallbacks even if APIs fail.
```

This is OK! The agent degrades gracefully.

## Quick Validation Checklist

- [ ] `python test_pumpfun_live.py` runs without crashes
- [ ] At least 1 trending token is fetched
- [ ] Generated tweets contain token references
- [ ] Cache speeds up repeated calls
- [ ] Logs show "Built ecosystem context"
- [ ] Agent runs normally: `python -m src.main`

## Success Criteria

**You'll know it's working when you see:**

1. ✅ Actual token symbols in tweets (e.g., $BONK, $DOGE)
2. ✅ Specific numbers (e.g., "12 launches", "3 rugs")
3. ✅ Current meta references (e.g., "dog season")
4. ✅ Logs showing data fetching
5. ✅ Different content on each generation (varied data)

**Example perfect output:**
```
Generated tweet:
------------------------------------------------------------
$BONK trending with 12 launches in the last hour and 3 rugs
in 24h. dog season hits different when the bonding curve is
your teacher 🐸📈
------------------------------------------------------------
```

If you see tweets like this ^ the integration is **PERFECT** ✨

---

*the frog knows what's trending anon, just test it 🐸*
