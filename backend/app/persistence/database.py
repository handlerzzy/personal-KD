"""SQLite connection management and table initialization."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None
_db: aiosqlite.Connection | None = None
_lock = asyncio.Lock()


def set_db_path(path: str | Path) -> None:
    """Set the database file path. Must be called before get_db()."""
    global _DB_PATH
    _DB_PATH = Path(path)


async def get_db() -> aiosqlite.Connection:
    """Get or create the singleton database connection with thread safety."""
    global _db
    async with _lock:
        if _db is None:
            if _DB_PATH is None:
                raise RuntimeError("Database path not set. Call set_db_path() first.")
            _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _db = await aiosqlite.connect(str(_DB_PATH))
            _db.row_factory = aiosqlite.Row
            await _db.execute("PRAGMA journal_mode=WAL")
            await _db.execute("PRAGMA busy_timeout=5000")
            await _db.execute("PRAGMA foreign_keys=ON")
            logger.info("SQLite connected: %s", _DB_PATH)
        return _db


async def reconnect() -> aiosqlite.Connection:
    """Reconnect to the database (useful after connection failure)."""
    global _db
    async with _lock:
        if _db is not None:
            try:
                await _db.close()
            except Exception:
                pass
            _db = None
    return await get_db()


async def init_db() -> None:
    """Create all tables if they don't exist."""
    db = await get_db()

    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            email TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

        CREATE TABLE IF NOT EXISTS token_blacklist (
            id TEXT PRIMARY KEY,
            token TEXT NOT NULL,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_token_blacklist_token ON token_blacklist(token);
        CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires ON token_blacklist(expires_at);

        CREATE TABLE IF NOT EXISTS knowledge_bases (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            doc_count INTEGER DEFAULT 0,
            conv_count INTEGER DEFAULT 0,
            user_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_kb_user_id ON knowledge_bases(user_id);

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            user_id TEXT,
            title TEXT NOT NULL DEFAULT '新对话',
            is_pinned INTEGER DEFAULT 0,
            message_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conv_user_id ON conversations(user_id);

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT DEFAULT '',
            reasoning_content TEXT DEFAULT '',
            sources TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_conversations_kb_id ON conversations(kb_id);
        CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conversation_id);
    """)

    # --- Schema migration: add missing columns to existing tables ---
    async with db.execute("PRAGMA table_info(conversations)") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if "is_pinned" not in cols:
        await db.execute("ALTER TABLE conversations ADD COLUMN is_pinned INTEGER DEFAULT 0")
        logger.info("Migration: added is_pinned column to conversations")
    if "message_count" not in cols:
        await db.execute("ALTER TABLE conversations ADD COLUMN message_count INTEGER DEFAULT 0")
        logger.info("Migration: added message_count column to conversations")
    if "updated_at" not in cols:
        await db.execute("ALTER TABLE conversations ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        await db.execute("UPDATE conversations SET updated_at = created_at WHERE updated_at = ''")
        logger.info("Migration: added updated_at column to conversations")

    async with db.execute("PRAGMA table_info(knowledge_bases)") as cur:
        kb_cols = {row[1] for row in await cur.fetchall()}
    if "updated_at" not in kb_cols:
        await db.execute(
            "ALTER TABLE knowledge_bases ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
        )
        await db.execute("UPDATE knowledge_bases SET updated_at = created_at WHERE updated_at = ''")
        logger.info("Migration: added updated_at column to knowledge_bases")

    async with db.execute("PRAGMA table_info(messages)") as cur:
        msg_cols = {row[1] for row in await cur.fetchall()}
    if "reasoning_content" not in msg_cols:
        await db.execute("ALTER TABLE messages ADD COLUMN reasoning_content TEXT DEFAULT ''")
        logger.info("Migration: added reasoning_content column to messages")
    if "sources" not in msg_cols:
        await db.execute("ALTER TABLE messages ADD COLUMN sources TEXT DEFAULT '[]'")
        logger.info("Migration: added sources column to messages")

    # --- Migration: add user_id to existing tables ---
    async with db.execute("PRAGMA table_info(knowledge_bases)") as cur:
        kb_cols = {row[1] for row in await cur.fetchall()}
    if "user_id" not in kb_cols:
        await db.execute(
            "ALTER TABLE knowledge_bases ADD COLUMN user_id"
            " TEXT REFERENCES users(id) ON DELETE SET NULL"
        )
        logger.info("Migration: added user_id column to knowledge_bases")

    async with db.execute("PRAGMA table_info(conversations)") as cur:
        conv_cols = {row[1] for row in await cur.fetchall()}
    if "user_id" not in conv_cols:
        await db.execute(
            "ALTER TABLE conversations ADD COLUMN user_id"
            " TEXT REFERENCES users(id) ON DELETE SET NULL"
        )
        logger.info("Migration: added user_id column to conversations")

    # --- Migration: add token_version to users for password change invalidation ---
    async with db.execute("PRAGMA table_info(users)") as cur:
        user_cols = {row[1] for row in await cur.fetchall()}
    if "token_version" not in user_cols:
        await db.execute("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0")
        logger.info("Migration: added token_version column to users")

    await db.commit()
    logger.info("Database tables initialized")


async def close_db() -> None:
    """Close the database connection."""
    global _db
    async with _lock:
        if _db is not None:
            await _db.close()
            _db = None
            logger.info("SQLite connection closed")
