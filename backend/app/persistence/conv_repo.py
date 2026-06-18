"""Conversation repository — CRUD operations for conversations."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from app.persistence.database import get_db

logger = logging.getLogger(__name__)


class ConvRepository:
    """Conversation persistence using SQLite."""

    @staticmethod
    async def create(kb_id: str, title: str = "新对话", user_id: str | None = None) -> dict:
        """Create a new conversation."""
        db = await get_db()
        now = datetime.now(UTC).isoformat()
        conv_id = secrets.token_hex(6)
        await db.execute(
            "INSERT INTO conversations"
            " (id, kb_id, user_id, title, created_at, updated_at,"
            " is_pinned, message_count)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
            (conv_id, kb_id, user_id, title, now, now),
        )
        # Update count in same transaction
        await db.execute(
            "UPDATE knowledge_bases SET conv_count = conv_count + 1, updated_at = ? WHERE id = ?",
            (now, kb_id),
        )
        await db.commit()
        return await ConvRepository.get(conv_id)

    @staticmethod
    async def get(conv_id: str) -> dict | None:
        """Get a conversation by ID."""
        db = await get_db()
        async with db.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            d = dict(row)
            d["is_pinned"] = bool(d.get("is_pinned", 0))
            return d

    @staticmethod
    async def list_by_kb(kb_id: str) -> list[dict]:
        """List all conversations for a KB, pinned first then by newest."""
        db = await get_db()
        async with db.execute(
            "SELECT * FROM conversations WHERE kb_id = ? ORDER BY is_pinned DESC, updated_at DESC",
            (kb_id,),
        ) as cur:
            rows = await cur.fetchall()
            result = [dict(r) for r in rows]
            for d in result:
                d["is_pinned"] = bool(d.get("is_pinned", 0))
            return result

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
    async def delete(conv_id: str) -> bool:
        """Delete a conversation (cascades to messages)."""
        db = await get_db()
        row = await db.execute_fetchall("SELECT kb_id FROM conversations WHERE id = ?", (conv_id,))
        if not row:
            return False
        kb_id = row[0]["kb_id"]
        now = datetime.now(UTC).isoformat()

        # Delete in single transaction for consistency
        await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await db.execute(
            "UPDATE knowledge_bases"
            " SET conv_count = MAX(conv_count - 1, 0), updated_at = ?"
            " WHERE id = ?",
            (now, kb_id),
        )
        await db.commit()

        logger.info("Conversation deleted: id=%s", conv_id)
        return True

    @staticmethod
    async def toggle_pin(conv_id: str) -> dict | None:
        """Toggle pin status of a conversation."""
        db = await get_db()
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE conversations"
            " SET is_pinned = CASE WHEN is_pinned = 1 THEN 0 ELSE 1 END,"
            " updated_at = ? WHERE id = ?",
            (now, conv_id),
        )
        await db.commit()
        return await ConvRepository.get(conv_id)


# Import at bottom to avoid circular imports
