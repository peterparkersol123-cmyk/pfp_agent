# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Pump.fun AI Agent                        │
│                                                             │
│  ┌──────────────┐      ┌──────────────┐                   │
│  │   Scheduler  │─────▶│ Main Agent   │                   │
│  │  (APSchedule)│      │ Orchestrator │                   │
│  └──────────────┘      └──────┬───────┘                   │
│                               │                             │
│                               ▼                             │
│                    ┌──────────────────┐                    │
│                    │ Content Pipeline │                    │
│                    └────────┬─────────┘                    │
│                             │                               │
│         ┌───────────────────┼───────────────────┐         │
│         ▼                   ▼                   ▼           │
│  ┌──────────┐      ┌──────────────┐    ┌──────────┐      │
│  │  Topic   │      │   Content    │    │  Content │      │
│  │ Manager  │      │  Generator   │    │Validator │      │
│  └────┬─────┘      └──────┬───────┘    └────┬─────┘      │
│       │                   │                  │             │
│       │                   ▼                  │             │
│       │           ┌──────────────┐          │             │
│       │           │ Claude API   │          │             │
│       │           │   Client     │          │             │
│       │           └──────────────┘          │             │
│       │                                     │             │
│       └──────────────┬──────────────────────┘             │
│                      ▼                                     │
│              ┌──────────────┐                             │
│              │  Twitter API │                             │
│              │   Client     │                             │
│              └──────┬───────┘                             │
│                     │                                      │
│                     ▼                                      │
│              ┌──────────────┐                             │
│              │   Database   │                             │
│              │   Manager    │                             │
│              └──────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

## Component Flow

### 1. Initialization
```
settings.py → Validate Config
    ↓
main.py → Initialize Components
    ↓
API Clients → Test Connections
    ↓
Database → Init Schema
    ↓
Scheduler → Start Background Jobs
```

### 2. Posting Cycle

```
Scheduler Triggers
    ↓
Topic Manager → Select Content Type
    ↓
Content Generator → Generate via Claude
    ↓
Content Validator → Validate Content
    ↓
Database → Check Duplicates
    ↓
Twitter Client → Post Tweet/Thread
    ↓
Database → Store Post Record
    ↓
Topic Manager → Update Statistics
    ↓
Scheduler → Schedule Next Post
```

## Module Breakdown

### Configuration Layer (`src/config/`)
- **Purpose**: Centralized configuration management
- **Key File**: `settings.py`
- **Features**: 
  - Environment variable loading
  - Validation logic
  - Default values
  - Production/debug modes

### API Layer (`src/api/`)
- **Purpose**: External API integrations
- **Components**:
  - `claude_client.py`: Claude API wrapper
  - `twitter_client.py`: Twitter API wrapper
- **Features**:
  - Connection testing
  - Retry logic
  - Rate limit handling
  - Error recovery

### Content Layer (`src/content/`)
- **Purpose**: Content creation and management
- **Components**:
  - `templates.py`: Prompt templates
  - `generator.py`: Content generation
  - `validator.py`: Content validation
- **Features**:
  - Multiple content types
  - Weighted selection
  - Thread support
  - Safety checks

### Strategy Layer (`src/strategy/`)
- **Purpose**: Intelligent posting decisions
- **Components**:
  - `scheduler.py`: Timing and frequency
  - `topic_manager.py`: Topic selection
- **Features**:
  - Smart scheduling
  - Topic rotation
  - Performance tracking
  - Rate limiting

### Database Layer (`src/database/`)
- **Purpose**: Persistent storage
- **Components**:
  - `models.py`: Data schemas
  - `operations.py`: CRUD operations
- **Features**:
  - Post history
  - Analytics
  - Topic tracking
  - Settings storage

### Utilities (`src/utils/`)
- **Purpose**: Shared functionality
- **Components**:
  - `logger.py`: Logging setup
  - `helpers.py`: Helper functions
- **Features**:
  - Colored logging
  - Text processing
  - Time utilities
  - Formatting

## Data Flow

### Content Generation Flow
```
User Request/Scheduler
    ↓
select_content_type() → Weighted Random Selection
    ↓
generate_tweet(type) → Build Prompt from Template
    ↓
Claude API Call → Generate Content
    ↓
validate(content) → Check Rules & Limits
    ↓
sanitize(content) → Auto-fix Issues
    ↓
Return Valid Content
```

### Posting Flow
```
Valid Content
    ↓
is_duplicate() → Check Database
    ↓
create_post() → Create DB Record (pending)
    ↓
post_tweet() → Twitter API Call
    ↓
update_post() → Update DB Record (posted/failed)
    ↓
update_topic_success() → Update Stats
```

## Database Schema

### Posts Table
```sql
posts
├── id (PK)
├── tweet_id
├── content
├── content_type
├── status (pending/posted/failed)
├── created_at
├── posted_at
├── likes
├── retweets
├── replies
├── is_thread
├── thread_id
└── error_message
```

### Topics Table
```sql
topics
├── id (PK)
├── topic_name
├── content_type
├── last_used
├── usage_count
├── success_rate
└── avg_engagement
```

### Settings Table
```sql
settings
├── id (PK)
├── key
├── value
└── updated_at
```

## Scheduling Architecture

```
APScheduler (Background)
    ↓
IntervalTrigger (base_interval)
    ↓
_post_wrapper()
    ├── can_post_now() → Rate Limit Check
    ├── post_callback() → Main Posting Logic
    └── reschedule() → Calculate Next Post
```

### Rate Limiting
```
Post Request
    ↓
Check Hourly Limit (count last 60 min)
    ↓
Check Daily Limit (count last 24 hours)
    ↓
Allow/Deny + Reason
```

## Error Handling Flow

```
API Call
    ↓
Try Execute
    ├─── Success → Return Result
    │
    └─── Error
           ├── Rate Limit → Backoff + Retry
           ├── Connection → Backoff + Retry
           ├── Client Error → Log + Fail
           └── Server Error → Backoff + Retry
```

## State Management

### Scheduler State
- Running/Stopped
- Next post time
- Current rate limits
- Background jobs

### Database State
- Post history
- Topic usage
- Engagement metrics
- Configuration

### Runtime State
- API clients
- Active connections
- Current execution
- Error counts

## Security Layers

### 1. Configuration
- Environment variables
- No hardcoded secrets
- Gitignored sensitive files

### 2. Validation
- Input sanitization
- Content filtering
- Length limits
- Pattern matching

### 3. Rate Limiting
- Per-hour limits
- Per-day limits
- API quotas
- Backoff delays

### 4. Error Handling
- Try-catch blocks
- Graceful degradation
- Logged failures
- Recovery mechanisms

## Deployment Architecture

### Development
```
Local Machine
    ↓
Virtual Environment
    ↓
Debug Mode (no posting)
    ↓
Console + File Logging
```

### Production
```
Server/Cloud
    ↓
Virtual Environment
    ↓
Production Mode
    ↓
Background Process (nohup/screen/systemd)
    ↓
File Logging
    ↓
Database Backups
```

## Monitoring Points

1. **Logs**: `logs/agent.log`
2. **Database**: `data/agent.db`
3. **Twitter**: Posted content
4. **Console**: Real-time output
5. **Scheduler**: Job status

## Extension Points

### Easy to Add:
- New content types (templates.py)
- Custom validators (validator.py)
- Additional API clients (api/)
- New database models (models.py)
- Custom helpers (helpers.py)

### Moderate Complexity:
- Image generation/posting
- Engagement auto-update
- Reply functionality
- Multiple accounts
- Web dashboard

### Advanced:
- Machine learning optimization
- A/B testing framework
- Distributed deployment
- Real-time analytics
- Advanced NLP features

## Performance Characteristics

- **Memory**: ~50MB base usage
- **CPU**: Low (mostly I/O wait)
- **Network**: Minimal (API calls only)
- **Storage**: SQLite (grows ~1KB per post)
- **Latency**: 2-5s per generation

## Scalability

### Current Limits:
- Single account
- Sequential posting
- Local SQLite
- Single process

### Can Scale To:
- Multiple accounts (modify clients)
- Parallel generation (threading)
- PostgreSQL (change DB)
- Multi-process (with coordination)

## Technology Decisions

### Why Python?
- Excellent AI/API libraries
- Easy to read and modify
- Great for automation
- Strong ecosystem

### Why SQLite?
- No server needed
- Simple setup
- Sufficient for use case
- Easy backups

### Why APScheduler?
- Pure Python
- Flexible triggers
- Background execution
- Job persistence

### Why Tweepy?
- Official Twitter library
- Twitter API v2 support
- Active maintenance
- Good documentation

### Why Anthropic SDK?
- Official Claude library
- Streaming support
- Type hints
- Well documented
