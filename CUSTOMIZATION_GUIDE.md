# Customization Guide

This guide explains how to customize the Pump.fun X/Twitter AI Agent to fit your needs.

## Content Templates

### Location
Content templates are defined in `src/content/templates.py`

### Adding New Content Types

1. Add a new content type to the `ContentType` enum:

```python
class ContentType(Enum):
    # ... existing types ...
    MY_NEW_TYPE = "my_new_type"
```

2. Create a new template:

```python
ContentTemplate(
    content_type=ContentType.MY_NEW_TYPE,
    system_prompt=PromptTemplates.BASE_SYSTEM_PROMPT,
    user_prompts=[
        "Create a tweet about...",
        "Write content focusing on...",
        "Generate a post that...",
    ],
    weight=2  # Adjust weight for frequency
)
```

3. Add it to the `TEMPLATES` list

### Modifying Existing Templates

Edit the `user_prompts` list for any template:

```python
user_prompts=[
    "Your custom prompt here",
    "Another variation",
    "And another...",
]
```

### Adjusting Content Weights

Higher weight = appears more frequently:

```python
ContentTemplate(
    # ...
    weight=5  # Will appear 5x more than weight=1 templates
)
```

## Posting Schedule

### Location
Configuration in `.env` and `src/config/settings.py`

### Adjust Posting Frequency

Edit `.env`:

```bash
# Post every hour
POST_INTERVAL_MINUTES=60

# Post every 3 hours
POST_INTERVAL_MINUTES=180

# Post every 30 minutes (fast!)
POST_INTERVAL_MINUTES=30
```

### Custom Posting Times

Modify `src/strategy/scheduler.py` to post at specific times:

```python
from apscheduler.triggers.cron import CronTrigger

# Post daily at 9 AM and 5 PM
self.scheduler.add_job(
    func=self._post_wrapper,
    trigger=CronTrigger(hour='9,17', minute='0'),
    args=[post_callback],
    id='post_job'
)
```

### Time Zone Settings

```python
from apscheduler.triggers.cron import CronTrigger

# Post at specific time in EST
trigger = CronTrigger(
    hour='9',
    minute='0',
    timezone='America/New_York'
)
```

## Content Validation

### Location
Validation rules in `src/content/validator.py`

### Customize Validation Rules

Edit `ContentValidator` class:

```python
class ContentValidator:
    def __init__(self):
        # Custom max length
        self.max_length = 280  # Or less for safety

        # Add custom prohibited patterns
        self.prohibited_patterns = [
            r'your_pattern_here',
            r'another_pattern',
        ]
```

### Add Custom Validations

```python
def validate(self, content: str) -> Tuple[bool, List[str]]:
    errors = []

    # ... existing validations ...

    # Add your custom validation
    if "banned_word" in content.lower():
        errors.append("Content contains banned word")

    # Check minimum length
    if len(content) < 50:
        errors.append("Content too short")

    return len(errors) == 0, errors
```

## Database Schema

### Location
Schema defined in `src/database/operations.py`

### Adding Custom Fields

1. Modify the `Post` model in `src/database/models.py`:

```python
@dataclass
class Post:
    # ... existing fields ...
    custom_field: str = ""
    engagement_score: float = 0.0
```

2. Update the database schema:

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        -- ... existing columns ...
        custom_field TEXT,
        engagement_score REAL DEFAULT 0.0
    )
""")
```

3. Update CRUD operations accordingly

### Adding New Tables

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS my_custom_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
```

## Topic Management

### Location
Topic selection logic in `src/strategy/topic_manager.py`

### Custom Topic Selection Algorithm

```python
def select_content_type(self) -> ContentType:
    # Your custom logic
    current_hour = datetime.now().hour

    # Post educational content in the morning
    if 6 <= current_hour < 12:
        return ContentType.EDUCATIONAL

    # Market analysis during trading hours
    elif 12 <= current_hour < 20:
        return ContentType.MARKET_ANALYSIS

    # Community content in the evening
    else:
        return ContentType.COMMUNITY_HIGHLIGHT
```

### Adjust Thread Frequency

```python
def should_post_thread(self) -> bool:
    # Always post threads
    return True

    # Never post threads
    return False

    # Post threads 50% of the time
    return random.random() < 0.5

    # Post threads only on weekends
    return datetime.now().weekday() >= 5
```

## Rate Limiting

### Location
Settings in `.env` and enforcement in `src/strategy/scheduler.py`

### Custom Rate Limits

Edit `.env`:

```bash
# Conservative (safer)
TWITTER_MAX_TWEETS_PER_DAY=20
TWITTER_MAX_TWEETS_PER_HOUR=5

# Moderate
TWITTER_MAX_TWEETS_PER_DAY=50
TWITTER_MAX_TWEETS_PER_HOUR=10

# Aggressive (not recommended)
TWITTER_MAX_TWEETS_PER_DAY=100
TWITTER_MAX_TWEETS_PER_HOUR=15
```

### Time-Based Rate Limiting

```python
def can_post_now(self) -> tuple[bool, Optional[str]]:
    # Don't post during night hours (UTC)
    current_hour = datetime.now().hour
    if 2 <= current_hour < 8:
        return False, "Night hours - paused"

    # ... existing checks ...
```

## Claude API Settings

### Location
Configuration in `src/config/settings.py` and `.env`

### Adjust Generation Parameters

Edit `.env`:

```bash
# Use different Claude model
CLAUDE_MODEL=claude-sonnet-4-5-20250929

# Adjust creativity (0.0 = deterministic, 1.0 = very creative)
CLAUDE_TEMPERATURE=0.8

# Maximum response length
CLAUDE_MAX_TOKENS=500
```

### Modify Generation Logic

In `src/content/generator.py`:

```python
# Generate with custom parameters
content = self.claude_client.generate_content(
    prompt=user_prompt,
    system_prompt=system_prompt,
    max_tokens=200,      # Shorter responses
    temperature=0.9      # More creative
)
```

## Logging

### Location
Logging setup in `src/utils/logger.py`

### Adjust Log Levels

Edit `.env`:

```bash
# Show everything (development)
LOG_LEVEL=DEBUG

# Normal operation
LOG_LEVEL=INFO

# Only warnings and errors
LOG_LEVEL=WARNING

# Only errors
LOG_LEVEL=ERROR
```

### Custom Log Formatting

```python
console_formatter = colorlog.ColoredFormatter(
    "%(log_color)s[%(levelname)s]%(reset)s %(message)s",
    # Your custom format
)
```

### Multiple Log Files

```python
# Add handler for error-only log
error_handler = logging.FileHandler('logs/errors.log')
error_handler.setLevel(logging.ERROR)
logger.addHandler(error_handler)
```

## Engagement Tracking

### Enable Auto-Fetching Engagement

Add to `src/main.py`:

```python
def update_engagement(self):
    """Fetch and update engagement metrics."""
    recent_posts = self.db.get_recent_posts(limit=10, status="posted")

    for post in recent_posts:
        if post.tweet_id and not post.tweet_id.startswith("debug"):
            try:
                # Fetch tweet
                tweet = self.twitter_client.client.get_tweet(
                    post.tweet_id,
                    tweet_fields=["public_metrics"]
                )

                if tweet.data:
                    metrics = tweet.data.get("public_metrics", {})

                    # Update database
                    self.db.update_post(
                        post.id,
                        likes=metrics.get("like_count", 0),
                        retweets=metrics.get("retweet_count", 0),
                        replies=metrics.get("reply_count", 0)
                    )
            except Exception as e:
                logger.error(f"Failed to fetch engagement for {post.tweet_id}: {e}")
```

Schedule it:

```python
self.scheduler.scheduler.add_job(
    func=self.update_engagement,
    trigger=IntervalTrigger(hours=1),
    id='engagement_job'
)
```

## Adding Media Support

### Image Posting

```python
def post_tweet_with_image(self, text: str, image_path: str):
    """Post tweet with image."""
    # Upload media
    media = self.api.media_upload(image_path)

    # Post with media
    response = self.client.create_tweet(
        text=text,
        media_ids=[media.media_id]
    )

    return response
```

### Generate Images with DALL-E

Integrate with OpenAI API to generate images for tweets.

## Custom Metrics

### Add Performance Tracking

```python
@dataclass
class Post:
    # ... existing fields ...
    virality_score: float = 0.0
    sentiment_score: float = 0.0

def calculate_virality(self, post: Post) -> float:
    """Calculate virality score."""
    engagement = post.likes + (post.retweets * 2) + (post.replies * 3)
    return engagement / max(1, (datetime.now() - post.posted_at).hours)
```

## Environment-Specific Configs

### Development Config

```bash
# .env.development
ENVIRONMENT=development
DEBUG=True
POST_INTERVAL_MINUTES=5
TWITTER_MAX_TWEETS_PER_HOUR=100
```

### Production Config

```bash
# .env.production
ENVIRONMENT=production
DEBUG=False
POST_INTERVAL_MINUTES=120
TWITTER_MAX_TWEETS_PER_HOUR=10
```

Load specific config:

```python
from dotenv import load_dotenv
load_dotenv('.env.production')
```

## Tips

1. **Test Changes**: Always test with `DEBUG=True` first
2. **Backup Database**: Before schema changes, backup your database
3. **Monitor Logs**: Check logs after customizations
4. **Version Control**: Use git to track your changes
5. **Start Small**: Make incremental changes and test each one
6. **Document**: Comment your customizations for future reference

## Examples

See `examples/` directory (if exists) for:
- Custom content templates
- Advanced scheduling
- Integration examples
- Custom validators
