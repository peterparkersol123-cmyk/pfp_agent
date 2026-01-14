# Setup Guide - Pump.fun X/Twitter AI Agent

This guide will walk you through setting up and running the Pump.fun X/Twitter AI Agent.

## Prerequisites

- Python 3.9 or higher
- pip (Python package installer)
- Git (optional, for cloning)

## Step 1: Get API Keys

### Claude API (Anthropic)

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key (you'll need it for `.env`)

### X/Twitter API

1. Go to [Twitter Developer Portal](https://developer.twitter.com/)
2. Create a developer account if you don't have one
3. Create a new project and app
4. Set up OAuth 1.0a with Read and Write permissions:
   - Go to your app settings
   - Navigate to "Keys and tokens"
   - Generate API Key and Secret
   - Generate Access Token and Secret
5. Copy all credentials:
   - API Key
   - API Secret
   - Access Token
   - Access Token Secret
   - Bearer Token (optional)

## Step 2: Install the Agent

### Option A: Using the run script (Recommended)

```bash
# Navigate to project directory
cd ClaudeXAgent

# Run the setup script
./run.sh
```

The script will:
- Create a virtual environment
- Install dependencies
- Create `.env` from template
- Prompt you to add API keys

### Option B: Manual installation

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 3: Configure Environment Variables

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your favorite editor:
   ```bash
   nano .env
   # or
   vim .env
   # or
   code .env
   ```

3. Fill in your API credentials:

   ```bash
   # Claude API
   ANTHROPIC_API_KEY=sk-ant-api03-...

   # Twitter API
   TWITTER_API_KEY=your_api_key_here
   TWITTER_API_SECRET=your_api_secret_here
   TWITTER_ACCESS_TOKEN=your_access_token_here
   TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret_here
   TWITTER_BEARER_TOKEN=your_bearer_token_here
   ```

4. Adjust settings (optional):

   ```bash
   # Posting frequency (in minutes)
   POST_INTERVAL_MINUTES=120

   # Rate limits
   TWITTER_MAX_TWEETS_PER_DAY=50
   TWITTER_MAX_TWEETS_PER_HOUR=10

   # Debug mode (set to False for production)
   DEBUG=True
   ```

## Step 4: Test the Agent

Before running the agent in production, test that everything works:

```bash
# Activate virtual environment if not already active
source venv/bin/activate

# Run test suite
python test_agent.py
```

The test suite will verify:
- ✓ Database initialization
- ✓ Claude API connection
- ✓ Twitter API connection
- ✓ Content generation
- ✓ Topic management
- ✓ Scheduler functionality

All tests should pass before proceeding.

## Step 5: Run the Agent

### Development Mode (Debug)

In debug mode, the agent generates content but doesn't actually post to Twitter:

```bash
# Make sure DEBUG=True in .env
python -m src.main
```

### Production Mode

When ready to post to Twitter:

1. Set `DEBUG=False` in `.env`
2. Run the agent:

   ```bash
   python -m src.main
   ```

3. The agent will:
   - Display initial statistics
   - Schedule the first post
   - Continue running and posting on schedule
   - Press `Ctrl+C` to stop

### Running in Background

For production deployment, run the agent in the background:

```bash
# Using nohup
nohup python -m src.main > logs/app.log 2>&1 &

# Or using screen
screen -S pumpfun-agent
python -m src.main
# Press Ctrl+A then D to detach

# Or using tmux
tmux new -s pumpfun-agent
python -m src.main
# Press Ctrl+B then D to detach
```

## Step 6: Monitor the Agent

### View Logs

```bash
# Real-time log monitoring
tail -f logs/agent.log

# View last 100 lines
tail -n 100 logs/agent.log

# Search logs
grep "ERROR" logs/agent.log
```

### Check Database

```bash
# Open SQLite database
sqlite3 data/agent.db

# View recent posts
sqlite> SELECT created_at, content FROM posts ORDER BY created_at DESC LIMIT 10;

# View engagement stats
sqlite> SELECT content_type, COUNT(*), AVG(likes + retweets) as avg_engagement
        FROM posts WHERE status='posted' GROUP BY content_type;

# Exit
sqlite> .quit
```

### Check Twitter

Monitor your Twitter account to see posted content and engagement.

## Troubleshooting

### "Claude API connection failed"

- Check that `ANTHROPIC_API_KEY` is set correctly in `.env`
- Verify your API key is active in Anthropic Console
- Check your API usage limits

### "Twitter API connection failed"

- Verify all Twitter credentials in `.env`
- Ensure your Twitter app has Read and Write permissions
- Check that tokens haven't expired
- Verify your developer account is in good standing

### "Rate limit reached"

- The agent has safety limits built in
- Adjust `TWITTER_MAX_TWEETS_PER_DAY` and `TWITTER_MAX_TWEETS_PER_HOUR` in `.env`
- Wait for the limit window to reset

### "Failed to generate content"

- Check Claude API quota
- Review logs for specific errors
- Try increasing `CLAUDE_MAX_TOKENS` in `.env`

### Database errors

```bash
# Reset database (WARNING: deletes all data)
rm data/agent.db
python -m src.main  # Will recreate database
```

## Configuration Options

### Posting Schedule

```bash
# Post every 2 hours (120 minutes)
POST_INTERVAL_MINUTES=120

# Minimum interval (prevents too-frequent posts)
MIN_INTERVAL_MINUTES=60

# Maximum interval
MAX_INTERVAL_MINUTES=240
```

### Content Settings

```bash
# Enable/disable hashtags
USE_HASHTAGS=True

# Maximum number of hashtags per tweet
MAX_HASHTAGS=3

# Maximum thread length
MAX_THREAD_TWEETS=5
```

### Rate Limiting

```bash
# Twitter limits (stay well under official limits)
TWITTER_MAX_TWEETS_PER_DAY=50
TWITTER_MAX_TWEETS_PER_HOUR=10

# Claude API limits
CLAUDE_MAX_REQUESTS_PER_MINUTE=50
```

## Best Practices

1. **Start in Debug Mode**: Always test with `DEBUG=True` first
2. **Monitor Initially**: Watch the agent closely for the first day
3. **Check Engagement**: Review which content types perform best
4. **Adjust Schedule**: Modify posting frequency based on your audience
5. **Stay Compliant**: Follow Twitter's automation rules
6. **Backup Data**: Regularly backup your `data/agent.db` file
7. **Update Prompts**: Customize templates in `src/content/templates.py`
8. **Review Logs**: Check logs daily for errors or issues

## Next Steps

- Customize content templates in `src/content/templates.py`
- Adjust topic weights for content variety
- Monitor engagement and optimize posting times
- Add custom content types
- Implement engagement tracking updates

## Support

For issues or questions:
- Check logs in `logs/agent.log`
- Review database in `data/agent.db`
- Consult Twitter API documentation
- Review Claude API documentation
