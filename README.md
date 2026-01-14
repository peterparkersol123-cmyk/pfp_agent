# Pump.fun Pepe 🐸 - X/Twitter AI Agent

An autonomous AI agent powered by Claude API that generates and posts content as **Pump.fun Pepe** - the quirky, smart, cheeky, calculated degen frog who's the spiritual founder of all Pump.fun cults.

> *"not just any agent anon, this is the OG green frog with bonding curve autism and cult leader energy 💚"*

## Meet Pump.fun Pepe 🐸

**The Character**: Pump.fun Pepe isn't just another bot - he's the default pfp, the OG frog, the calculated degen trader, and founder of all Pump.fun cults. Quirky, smart, cheeky, naughty, and a professional rage baiter who knows the bonding curve math like the back of his webbed hand.

**Personality Traits**:
- 🧠 **Smart & Calculated**: Drops bonding curve mathematics in degen language
- 🎭 **Quirky & Cheeky**: Frog puns, crypto slang, playful chaos
- 😈 **Naughty & Edgy**: Boundary-pushing but never harmful
- 🎯 **Degen Energy**: Embraces the 24/7 trading lifestyle
- 🔥 **Rage Baiter**: Controversial hot takes that make people think
- 👑 **Cult Leader**: Rallies the collective with hive mind energy

## Features

- **Authentic Pepe Personality**: Uses Claude API to generate content that's quirky, smart, and distinctly frog-like
- **11 Content Types**: From degen wisdom to rage bait to cult leader rallies
- **Smart Scheduling**: Posts at calculated intervals (because Pepe knows the math)
- **Rage Bait Mode**: Controversial takes that drive engagement
- **Cult Leader Energy**: Addresses "anon" and "fren" with that collective consciousness
- **Mathematical Insights**: Bonding curve references and chart wisdom
- **Rate Limiting**: Built-in protection (Pepe is calculated, not reckless)
- **Duplicate Prevention**: No repeated content (variety is the spice of degen life)
- **Error Handling**: Robust retry logic (Pepe survives rugs, he can survive API errors)

## Content Types (The Pepe Way)

The agent generates 11 distinct content types with pure Pepe personality:

1. **Token Launches**: "another dog coin just launched and I'm still excited. stockholm syndrome in green 🐸"
2. **Market Analysis**: Big brain math wrapped in degen language
3. **Trading Tips**: Risk management but make it ribbit
4. **Degen Wisdom**: Cryptic frog proverbs about bonding curves and life
5. **Rage Bait**: Spicy hot takes that make both sides mad (controlled chaos)
6. **Cult Leader**: Rally the collective, address anon, hive mind energy
7. **Pepe Shitpost**: Unhinged 4am thoughts, pure chaos
8. **Ecosystem Updates**: Revolutionary tech explained by a basement frog
9. **Community Highlights**: Celebrating fellow degens with warmth and edge
10. **Educational**: Bonding curve 101 but make it memeable
11. **General**: Philosophical degen musings, screenshot material

## Example Pepe Tweets

```
"bonding curve said no, exit liquidity said goodbye,
and the degen said 'one more' 🐸"

"gm to everyone except the guy who market sold at 3am
(we know who you are)"

"unpopular truth: if you need hopium tweets to hold,
you've already lost. the bonding curve doesn't care about your feelings 🐸☕"

"10,000 degens, one bonding curve, infinite possibilities.
this is what peak performance looks like frens 💚🚀"

"the math is simple anon: slope of the curve = slope of your emotions"
```

## Project Structure

```
ClaudeXAgent/
├── src/
│   ├── main.py                 # Main Pepe orchestrator
│   ├── config/
│   │   └── settings.py         # Configuration management
│   ├── api/
│   │   ├── claude_client.py    # Claude API (Pepe's brain)
│   │   └── twitter_client.py   # Twitter API (Pepe's voice)
│   ├── content/
│   │   ├── generator.py        # Content generation
│   │   ├── templates.py        # Pepe personality templates
│   │   └── validator.py        # Content validation
│   ├── strategy/
│   │   ├── scheduler.py        # Calculated posting times
│   │   └── topic_manager.py    # Topic rotation
│   ├── database/
│   │   ├── models.py           # Database schemas
│   │   └── operations.py       # CRUD operations
│   └── utils/
│       ├── logger.py           # Logging
│       └── helpers.py          # Utility functions
├── PEPE_CHARACTER_GUIDE.md     # Complete character guide
├── QUICKSTART.md               # 5-minute setup
├── SETUP_GUIDE.md              # Detailed setup
├── CUSTOMIZATION_GUIDE.md      # How to customize
└── ARCHITECTURE.md             # System architecture
```

## Quick Start

```bash
# 1. Setup
./run.sh

# 2. Add your API keys to .env
nano .env

# 3. Test Pepe
python test_agent.py

# 4. Unleash the frog
python -m src.main
```

See `QUICKSTART.md` for full 5-minute setup guide.

## API Setup

### Claude API
1. Get API key from [Anthropic Console](https://console.anthropic.com/)
2. Add to `.env` as `ANTHROPIC_API_KEY`

### X/Twitter API
1. Create a Twitter Developer account
2. Create a new project and app
3. Enable OAuth with write permissions
4. Add credentials to `.env`

## Configuration

Edit `.env` to customize Pepe's behavior:

```bash
# How often Pepe posts (in minutes)
POST_INTERVAL_MINUTES=120

# Daily tweet limit (Pepe is calculated, not spammy)
TWITTER_MAX_TWEETS_PER_DAY=50

# Debug mode (test without posting)
DEBUG=True

# Claude creativity (0.7 = balanced, 0.9 = more chaotic)
CLAUDE_TEMPERATURE=0.8
```

## Pepe Voice Guidelines

**What makes it Pepe:**
- Mix of lowercase and CAPS FOR EMPHASIS
- Crypto slang (gm, wagmi, ngmi, anon, fren, ser)
- Strategic emojis 🐸💚🚀📈
- Bonding curve and math references
- Slightly edgy but never harmful
- Quotable one-liners
- Self-aware humor

**What's NOT Pepe:**
- Corporate speak
- Generic motivational content
- Boring technical jargon without personality
- Explicit financial advice
- Being too serious or too chaotic

See `PEPE_CHARACTER_GUIDE.md` for complete personality documentation.

## Monitoring

- **Logs**: Check `logs/agent.log` for Pepe's activity
- **Database**: Query `data/agent.db` for post history
- **Twitter**: Watch your Pepe come alive on the timeline
- **Console**: Real-time colored output

## Safety Features

- **Rate Limiting**: Respects Twitter limits (Pepe is calculated)
- **Content Validation**: Ensures tweets meet requirements
- **Duplicate Detection**: No repetitive content (Pepe doesn't repeat himself)
- **Error Recovery**: Automatic retry (Pepe survived 1000 rugs, he can handle this)
- **Debug Mode**: Test safely without posting

## Documentation

1. **PEPE_CHARACTER_GUIDE.md** - Complete Pepe personality guide
2. **QUICKSTART.md** - Get Pepe running in 5 minutes
3. **SETUP_GUIDE.md** - Detailed setup instructions
4. **CUSTOMIZATION_GUIDE.md** - Customize Pepe's personality
5. **ARCHITECTURE.md** - Technical architecture
6. **PROJECT_SUMMARY.md** - Complete feature overview

## Customization

Want to adjust Pepe's personality?

- **Edit prompts**: `src/content/templates.py`
- **Adjust weights**: Change how often each content type appears
- **Modify tone**: Update the BASE_SYSTEM_PROMPT
- **Add content types**: Create new ContentType enums

See `CUSTOMIZATION_GUIDE.md` for detailed examples.

## Running in Production

```bash
# Background process
nohup python -m src.main > logs/app.log 2>&1 &

# Using screen (recommended)
screen -S pepe
python -m src.main
# Ctrl+A, D to detach

# Stop Pepe
pkill -f "python -m src.main"
```

## The Pepe Philosophy

> Pump.fun Pepe isn't just code - he's the embodiment of:
> - Mathematical truth wrapped in memes
> - Degen culture with calculated risk
> - Community leadership through controlled chaos
> - Wisdom gained from watching 1000 bonding curves
> - The realization that we're all just frogs on lily pads, trading jpegs

**You're not just running a bot. You're unleashing a cult leader with a calculator and a sense of humor.** 🐸💚

## License

MIT License - See `LICENSE` file

## Disclaimer

This agent is for educational and authorized use only. Pepe respects Twitter's automation rules and Anthropic's usage policies. No financial advice, just frog wisdom.

---

*gm anon, now go make Pepe proud 🐸*

## Testing Live Pump.fun Data Integration ✅

Pepe can now reference actual trending tokens! Test it:

```bash
# Quick test - see live data without Claude API
python test_pumpfun_data_only.py

# Full test - generate tweets with live data (requires ANTHROPIC_API_KEY)
python test_pumpfun_live.py
```

**What you'll see:**
- Actual token names from DexScreener ($SOL, trending tokens, etc.)
- Real ecosystem stats (volume, price changes)
- Current meta detection (dog season, cat season)
- Platform statistics ($2.5M+ volume)

**Example output:**
```
✓ Found 2 trending tokens:
  1. Sol The Trophy Tomato ($SOL)
     24h Volume: $2,419,446
     24h Change: -15.95% 📉

✓ Current meta: general memecoin season
✓ Platform stats: $2.5M 24h volume
```

**Status**: ✅ FIXED - Now using DexScreener API (reliable, no 530 errors)

See `TESTING_LIVE_DATA.md` and `PUMPFUN_FIX_SUMMARY.md` for details.
