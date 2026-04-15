"""Database initialization and schema management."""

from pathlib import Path
import logging

from database.connection import db

logger = logging.getLogger(__name__)


DDL_SQL = """
-- Summaries table
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    auto_tags TEXT DEFAULT '[]',
    model_used TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_summaries_thread_id ON summaries(thread_id);

-- Bookmarks table
CREATE TABLE IF NOT EXISTS bookmarks (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);
CREATE INDEX IF NOT EXISTS idx_bookmarks_thread_id ON bookmarks(thread_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_created ON bookmarks(created_at DESC);

-- Tags table
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT 'custom',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);

-- Bookmark-Tags junction table
CREATE TABLE IF NOT EXISTS bookmark_tags (
    bookmark_id TEXT NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (bookmark_id, tag_id)
);

-- Notes table
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmark_id TEXT NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);
CREATE INDEX IF NOT EXISTS idx_notes_bookmark ON notes(bookmark_id);

-- LLM logs table
CREATE TABLE IF NOT EXISTS llm_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    last_login TEXT
);

-- Config table
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);

-- FTS5 virtual table for full-text search
-- Uses trigram tokenizer so that CJK queries work without a third-party
-- tokenizer. Requires SQLite >= 3.34 (Python 3.12 ships 3.47+).
CREATE VIRTUAL TABLE IF NOT EXISTS bookmarks_fts USING fts5(
    title, summary, content=bookmarks, content_rowid=rowid, tokenize='trigram'
);

-- Triggers to keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS bookmarks_ai AFTER INSERT ON bookmarks BEGIN
    INSERT INTO bookmarks_fts(rowid, title, summary)
    VALUES (new.rowid, new.title, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS bookmarks_ad AFTER DELETE ON bookmarks BEGIN
    INSERT INTO bookmarks_fts(bookmarks_fts, rowid, title, summary)
    VALUES ('delete', old.rowid, old.title, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS bookmarks_au AFTER UPDATE ON bookmarks BEGIN
    INSERT INTO bookmarks_fts(bookmarks_fts, rowid, title, summary)
    VALUES ('delete', old.rowid, old.title, old.summary);
    INSERT INTO bookmarks_fts(rowid, title, summary)
    VALUES (new.rowid, new.title, new.summary);
END;

-- ============================================================
-- Phase 1: Memory System Tables
-- ============================================================

-- User profile: AI-inferred + manually-set user traits
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    profile_key TEXT NOT NULL,
    profile_value TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'auto',
    confidence REAL DEFAULT 0.8,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    UNIQUE(user_id, profile_key)
);

-- Persistent chat sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    thread_id TEXT,
    page_url TEXT,
    page_title TEXT,
    message_count INTEGER DEFAULT 0,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_thread ON chat_sessions(thread_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at DESC);

-- Chat messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);

-- Chat messages FTS5 index
CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(
    content, content=chat_messages, content_rowid=rowid, tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS chat_msg_ai AFTER INSERT ON chat_messages BEGIN
    INSERT INTO chat_messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chat_msg_ad AFTER DELETE ON chat_messages BEGIN
    INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
    VALUES ('delete', old.rowid, old.content);
END;

-- Strategy entities extracted from posts
CREATE TABLE IF NOT EXISTS strategy_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    name TEXT NOT NULL,
    strategy_type TEXT,
    asset_class TEXT,
    structured_data TEXT NOT NULL DEFAULT '{}',
    model_used TEXT,
    confidence REAL DEFAULT 0.7,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    UNIQUE(thread_id, name)
);
CREATE INDEX IF NOT EXISTS idx_strategy_thread ON strategy_entities(thread_id);
CREATE INDEX IF NOT EXISTS idx_strategy_type ON strategy_entities(strategy_type);

-- Reading history
CREATE TABLE IF NOT EXISTS reading_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    duration_seconds INTEGER DEFAULT 0,
    summary_generated INTEGER DEFAULT 0,
    bookmarked INTEGER DEFAULT 0,
    scroll_depth REAL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);
CREATE INDEX IF NOT EXISTS idx_reading_thread ON reading_history(thread_id);
CREATE INDEX IF NOT EXISTS idx_reading_created ON reading_history(created_at DESC);

-- Memory items: Hermes-style curated memories
CREATE TABLE IF NOT EXISTS memory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    source_session_id TEXT,
    source_thread_id TEXT,
    importance INTEGER DEFAULT 3,
    is_active INTEGER DEFAULT 1,
    last_accessed_at TEXT,
    access_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours'))
);
CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_items(memory_type, is_active);
CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory_items(importance DESC, access_count DESC);
"""


async def init_database(db_path: Path = None) -> None:
    """Initialize database with schema."""
    await db.initialize(db_path)

    # Upgrade the FTS5 table in place if it was created with the old default
    # (simple) tokenizer before we switched to trigram. We drop and let the
    # DDL below re-create it; the `rebuild` command then repopulates from the
    # external content table (bookmarks).
    await _migrate_bookmarks_fts()

    # Execute DDL using executescript equivalent
    await db.executescript(DDL_SQL)

    # Force-populate the FTS index from the external content table. This is a
    # no-op on a fresh DB (bookmarks is empty) but guarantees that, after a
    # schema upgrade, existing bookmarks are re-indexed with the new tokenizer.
    try:
        await db.execute("INSERT INTO bookmarks_fts(bookmarks_fts) VALUES ('rebuild')")
    except Exception as e:
        logger.warning(f"FTS rebuild skipped: {e}")

    # Insert default tags
    default_tags = [
        ("量化策略", "system"),
        ("因子分析", "system"),
        ("回测", "system"),
        ("数据分析", "system"),
        ("Python", "system"),
        ("机器学习", "system"),
        ("重要", "system"),
        ("待读", "system"),
    ]
    
    for name, category in default_tags:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                (name, category)
            )
        except Exception:
            pass  # Ignore if already exists

    # Create default admin account
    await _ensure_default_admin()


async def _migrate_bookmarks_fts() -> None:
    """Drop legacy FTS5 tables that were built with the default tokenizer.

    CREATE VIRTUAL TABLE IF NOT EXISTS is a no-op when the table already
    exists, even if the options diverge — so a simple DDL re-run would leave
    an old, Chinese-broken `bookmarks_fts` in place. We inspect the stored
    CREATE statement and drop it if it lacks the trigram tokenizer so the
    subsequent DDL rebuilds it fresh.
    """
    try:
        row = await db.fetchone(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='bookmarks_fts'"
        )
    except Exception:
        return

    if not row:
        return

    sql = (row["sql"] or "").lower()
    if "trigram" in sql:
        return

    logger.info("Upgrading bookmarks_fts to trigram tokenizer")
    # FTS5 shadow tables must be dropped via DROP TABLE on the virtual name;
    # SQLite cleans up the backing _config/_data/_idx tables automatically.
    await db.execute("DROP TABLE bookmarks_fts")


async def _ensure_default_admin(password_override: str | None = None) -> None:
    """Create default admin account if no admin exists.

    Args:
        password_override: If set, use this password (for tests).
            Otherwise generate a random one and print to stdout.
    """
    try:
        existing = await db.fetchone(
            "SELECT id FROM users WHERE username = ?", ("admin",)
        )
        if existing:
            return

        import secrets
        import bcrypt
        import os
        password = password_override or os.getenv("QUANTCLASS_ADMIN_PASSWORD") or secrets.token_urlsafe(16)
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        await db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", password_hash, "admin")
        )
        show_banner = not password_override and not os.getenv("QUANTCLASS_ADMIN_PASSWORD")
        if show_banner:
            # Print to stdout only — not to log files
            print("\n" + "=" * 50)
            print("  Default admin account created")
            print(f"  Username: admin")
            print(f"  Password: {password}")
            print("  Please change this password after first login!")
            print("=" * 50 + "\n")
        logger.info("Default admin account created (username: admin)")
    except Exception as e:
        logger.warning(f"Failed to create default admin: {e}")


async def close_database() -> None:
    """Close database connection."""
    await db.close()
