"""Conversation repository — CRUD operations for conversations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.persistence.database import get_db

logger = logging.getLogger(__name__)


class ConvRepository:
    """Conversation persistence using SQLite."""

    @staticmethod
    async def create(kb_id: str, title: str = "新对话") -> dict:
        """Create a new conversation."""
        db = await get_db()
        conv_id = uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        await db.execute(
            "INSERT INTO conversations"
            " (id, kb_id, title, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (conv_id, kb_id, title, now, now),
        )
        await db.commit()

        # Update KB conv count
        await KbRepository.update_conv_count(kb_id)

        logger.info("Conversation created: id=%s, kb_id=%s", conv_id, kb_id)
        return {
            "id": conv_id,
            "kb_id": kb_id,
            "title": title,
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    async def get(conv_id: str) -> dict | None:
        """Get a conversation by ID."""
        db = await get_db()
        async with db.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return dict(row)

    @staticmethod
    async def list_by_kb(kb_id: str) -> list[dict]:
        """List all conversations for a KB, newest first."""
        db = await get_db()
        async with db.execute(
            "SELECT * FROM conversations WHERE kb_id = ? ORDER BY updated_at DESC",
            (kb_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    async def update_title(conv_id: str, title: str) -> None:
        """Update conversation title."""
        db = await get_db()
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, conv_id),
        )
        await db.commit()

    @staticmethod
    async def update_message_count(conv_id: str) -> None:
        """Recalculate message count from messages table."""
        db = await get_db()
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conv_id,)
        ) as cur:
            count = (await cur.fetchone())[0]
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE conversations SET message_count = ?, updated_at = ? WHERE id = ?",
            (count, now, conv_id),
        )
        await db.commit()

    @staticmethod
    async def delete(conv_id: str) -> None:
        """Delete a conversation (cascades to messages)."""
        db = await get_db()
        # Get kb_id before deleting for conv count update
        async with db.execute("SELECT kb_id FROM conversations WHERE id = ?", (conv_id,)) as cur:
            row = await cur.fetchone()
            kb_id = row["kb_id"] if row else None

        await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await db.commit()

        if kb_id:
            await KbRepository.update_conv_count(kb_id)

        logger.info("Conversation deleted: id=%s", conv_id)


# Import at bottom to avoid circular imports
from app.persistence.kb_repo import KbRepository  # noqa: E402
