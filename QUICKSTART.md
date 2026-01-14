# Quick Start Guide

Get your Pump.fun X/Twitter AI Agent up and running in 5 minutes!

## Prerequisites

- Python 3.9+
- Claude API key (from [Anthropic Console](https://console.anthropic.com/))
- Twitter API credentials (from [Twitter Developer Portal](https://developer.twitter.com/))

## 1. Setup (2 minutes)

```bash
# Clone or navigate to the project
cd ClaudeXAgent

# Run the setup script
./run.sh
```

This will:
- Create a virtual environment
- Install all dependencies
- Create a `.env` file from template

## 2. Configure API Keys (1 minute)

Edit the `.env` file:

```bash
nano .env
```

Add your API keys:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-api03-...
TWITTER_API_KEY=your_key
TWITTER_API_SECRET=your_secret
TWITTER_ACCESS_TOKEN=your_token
TWITTER_ACCESS_TOKEN_SECRET=your_token_secret
TWITTER_BEARER_TOKEN=your_bearer_token

# Optional - Adjust posting frequency
POST_INTERVAL_MINUTES=120  # Post every 2 hours
DEBUG=True  # Set to False for production
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter` in nano)

## 3. Test Everything (1 minute)

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
python test_agent.py
```

All tests should pass ✓

## 4. Run the Agent (1 minute)

### Test Mode (Doesn't post to Twitter)

```bash
# Make sure DEBUG=True in .env
python -m src.main
```

The agent will:
- Generate content
- Show you what it would post
- NOT actually post to Twitter

### Production Mode (Actually posts)

```bash
# Set DEBUG=False in .env
python -m src.main
```

The agent will:
- Generate and post content automatically
- Follow your configured schedule
- Run until you stop it (Ctrl+C)

## 5. Monitor

Watch the agent work:

```bash
# In another terminal, watch logs
tail -f logs/agent.log

# View recent posts in database
sqlite3 data/agent.db "SELECT created_at, content FROM posts ORDER BY created_at DESC LIMIT 5;"
```

## That's It! 🎉

Your agent is now running. Here's what happens next:

1. **First Post**: Scheduled within 2 hours (or your configured interval)
2. **Continuous Operation**: Agent keeps running and posting on schedule
3. **Smart Content**: Automatically varies topics and styles
4. **Rate Limited**: Respects Twitter API limits automatically

## Common Commands

```bash
# Start the agent
python -m src.main

# Run tests
python test_agent.py

# View logs
tail -f logs/agent.log

# Stop the agent
# Press Ctrl+C in the terminal running the agent
```

## Next Steps

- **Customize Content**: Edit `src/content/templates.py` to customize tweets
- **Adjust Schedule**: Change `POST_INTERVAL_MINUTES` in `.env`
- **Monitor Performance**: Check Twitter for engagement on your posts
- **Read Full Docs**: See `SETUP_GUIDE.md` and `CUSTOMIZATION_GUIDE.md`

## Troubleshooting

### Agent won't start
- Check that all API keys are set in `.env`
- Run `python test_agent.py` to identify issues

### No posts appearing
- Verify `DEBUG=False` in `.env` for production mode
- Check `logs/agent.log` for errors
- Ensure you haven't hit rate limits

### API errors
- Verify API keys are correct and active
- Check API quota/usage limits
- Review Twitter app permissions (needs Read + Write)

## Getting Help

1. Check `logs/agent.log` for error messages
2. Review the full guides:
   - `SETUP_GUIDE.md` - Detailed setup instructions
   - `CUSTOMIZATION_GUIDE.md` - How to customize
   - `README.md` - Project overview

## Important Notes

- **Start in DEBUG mode** to test without posting
- **Monitor the first day** to ensure everything works
- **Follow Twitter rules** for automation
- **Keep API keys secure** - never commit `.env` to git
- **Backup your database** regularly (`data/agent.db`)

Enjoy your autonomous AI agent! 🚀
