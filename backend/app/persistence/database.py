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
        CREATE TABLE IF NOT EXISTS knowledge_bases (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            doc_count INTEGER DEFAULT 0,
            conv_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '新对话',
            message_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
        );

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

    await db.commit()
    logger.info("Database tables initialized")


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
        logger.info("SQLite connection closed")
