"""
Database operations for the agent.
Handles all CRUD operations and database initialization.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from src.config.settings import settings
from src.database.models import Post, Topic, Setting
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Manages database operations."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path or settings.DATABASE_PATH
        self.init_database()
        logger.info(f"Initialized DatabaseManager with database: {self.db_path}")

    @contextmanager
    def get_connection(self):
        """Get database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_database(self):
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Posts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tweet_id TEXT UNIQUE,
                    content TEXT NOT NULL,
                    content_type TEXT DEFAULT 'general',
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    posted_at TIMESTAMP,
                    likes INTEGER DEFAULT 0,
                    retweets INTEGER DEFAULT 0,
                    replies INTEGER DEFAULT 0,
                    is_thread BOOLEAN DEFAULT 0,
                    thread_id TEXT,
                    error_message TEXT
                )
            """)

            # Topics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_name TEXT UNIQUE NOT NULL,
                    content_type TEXT DEFAULT 'general',
                    last_used TIMESTAMP,
                    usage_count INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 0.0,
                    avg_engagement REAL DEFAULT 0.0
                )
            """)

            # Settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_content_type ON posts(content_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_topics_last_used ON topics(last_used)")

            conn.commit()
            logger.info("Database schema initialized successfully")

    # Post operations
    def create_post(self, post: Post) -> int:
        """
        Create a new post record.

        Args:
            post: Post object

        Returns:
            ID of created post
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO posts (tweet_id, content, content_type, status, created_at,
                                   posted_at, is_thread, thread_id, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post.tweet_id,
                post.content,
                post.content_type,
                post.status,
                post.created_at or datetime.now(),
                post.posted_at,
                post.is_thread,
                post.thread_id,
                post.error_message
            ))
            conn.commit()
            post_id = cursor.lastrowid
            logger.debug(f"Created post with ID: {post_id}")
            return post_id

    def update_post(self, post_id: int, **kwargs) -> bool:
        """
        Update a post record.

        Args:
            post_id: Post ID
            **kwargs: Fields to update

        Returns:
            True if successful
        """
        if not kwargs:
            return False

        fields = ", ".join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [post_id]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE posts SET {fields} WHERE id = ?", values)
            conn.commit()
            logger.debug(f"Updated post {post_id}")
            return cursor.rowcount > 0

    def get_post(self, post_id: int) -> Optional[Post]:
        """Get post by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_post(row)
            return None

    def get_recent_posts(self, limit: int = 10, status: Optional[str] = None) -> List[Post]:
        """
        Get recent posts.

        Args:
            limit: Maximum number of posts
            status: Filter by status (optional)

        Returns:
            List of posts
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM posts WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            rows = cursor.fetchall()
            return [self._row_to_post(row) for row in rows]

    def get_posts_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        status: Optional[str] = None
    ) -> List[Post]:
        """Get posts within date range."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT * FROM posts
                    WHERE created_at BETWEEN ? AND ? AND status = ?
                    ORDER BY created_at DESC
                """, (start_date, end_date, status))
            else:
                cursor.execute("""
                    SELECT * FROM posts
                    WHERE created_at BETWEEN ? AND ?
                    ORDER BY created_at DESC
                """, (start_date, end_date))
            rows = cursor.fetchall()
            return [self._row_to_post(row) for row in rows]

    def count_posts_in_timeframe(self, hours: int) -> int:
        """Count posts in the last N hours."""
        since = datetime.now() - timedelta(hours=hours)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM posts WHERE created_at > ? AND status = 'posted'",
                (since,)
            )
            return cursor.fetchone()[0]

    def is_duplicate_content(self, content: str, hours: int = 24) -> bool:
        """
        Check if similar content was posted recently.

        Args:
            content: Content to check
            hours: Time window in hours

        Returns:
            True if duplicate found
        """
        since = datetime.now() - timedelta(hours=hours)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM posts
                WHERE content = ? AND created_at > ? AND status = 'posted'
            """, (content, since))
            count = cursor.fetchone()[0]
            return count > 0

    # Topic operations
    def create_or_update_topic(self, topic: Topic) -> int:
        """Create or update a topic."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO topics (topic_name, content_type, last_used, usage_count,
                                    success_rate, avg_engagement)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic_name) DO UPDATE SET
                    last_used = excluded.last_used,
                    usage_count = excluded.usage_count,
                    success_rate = excluded.success_rate,
                    avg_engagement = excluded.avg_engagement
            """, (
                topic.topic_name,
                topic.content_type,
                topic.last_used or datetime.now(),
                topic.usage_count,
                topic.success_rate,
                topic.avg_engagement
            ))
            conn.commit()
            return cursor.lastrowid

    def get_topic(self, topic_name: str) -> Optional[Topic]:
        """Get topic by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM topics WHERE topic_name = ?", (topic_name,))
            row = cursor.fetchone()
            if row:
                return self._row_to_topic(row)
            return None

    def get_least_used_topics(self, limit: int = 5) -> List[Topic]:
        """Get least recently used topics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM topics
                ORDER BY last_used ASC NULLS FIRST, usage_count ASC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [self._row_to_topic(row) for row in rows]

    # Settings operations
    def get_setting(self, key: str) -> Optional[str]:
        """Get setting value by key."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

    def set_setting(self, key: str, value: str) -> bool:
        """Set setting value."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
            """, (key, value, datetime.now()))
            conn.commit()
            return True

    # Analytics
    def get_engagement_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get engagement statistics for the last N days."""
        since = datetime.now() - timedelta(days=days)
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total posts
            cursor.execute(
                "SELECT COUNT(*) FROM posts WHERE posted_at > ? AND status = 'posted'",
                (since,)
            )
            total_posts = cursor.fetchone()[0]

            # Total engagement
            cursor.execute("""
                SELECT
                    COALESCE(SUM(likes), 0) as total_likes,
                    COALESCE(SUM(retweets), 0) as total_retweets,
                    COALESCE(SUM(replies), 0) as total_replies
                FROM posts
                WHERE posted_at > ? AND status = 'posted'
            """, (since,))
            row = cursor.fetchone()

            # Average engagement
            avg_engagement = 0
            if total_posts > 0:
                total_engagement = row[0] + row[1] + row[2]
                avg_engagement = total_engagement / total_posts

            return {
                "total_posts": total_posts,
                "total_likes": row[0],
                "total_retweets": row[1],
                "total_replies": row[2],
                "avg_engagement": avg_engagement,
                "days": days
            }

    # Helper methods
    def _row_to_post(self, row: sqlite3.Row) -> Post:
        """Convert database row to Post object."""
        return Post(
            id=row["id"],
            tweet_id=row["tweet_id"],
            content=row["content"],
            content_type=row["content_type"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            posted_at=datetime.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
            likes=row["likes"],
            retweets=row["retweets"],
            replies=row["replies"],
            is_thread=bool(row["is_thread"]),
            thread_id=row["thread_id"],
            error_message=row["error_message"]
        )

    def _row_to_topic(self, row: sqlite3.Row) -> Topic:
        """Convert database row to Topic object."""
        return Topic(
            id=row["id"],
            topic_name=row["topic_name"],
            content_type=row["content_type"],
            last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
            usage_count=row["usage_count"],
            success_rate=row["success_rate"],
            avg_engagement=row["avg_engagement"]
        )
