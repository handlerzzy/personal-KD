"""Message repository — CRUD operations for messages."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.persistence.database import get_db

logger = logging.getLogger(__name__)


class MessageRepository:
    """Message persistence using SQLite."""

    @staticmethod
    async def add_message(
        conversation_id: str,
        role: str,
        content: str = "",
        reasoning_content: str = "",
        sources: list[dict] | None = None,
    ) -> dict:
        """Add a new message to a conversation."""
        db = await get_db()
        msg_id = uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()
        sources_json = json.dumps(sources or [], ensure_ascii=False)

        await db.execute(
            "INSERT INTO messages"
            " (id, conversation_id, role, content, reasoning_content, sources, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                msg_id,
                conversation_id,
                role,
                content,
                reasoning_content,
                sources_json,
                now,
            ),
        )
        await db.commit()

        # Update conversation message count and timestamp
        from app.persistence.conv_repo import ConvRepository
        await ConvRepository.update_message_count(conversation_id)

        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "reasoning_content": reasoning_content,
            "sources": sources or [],
            "created_at": now,
        }

    @staticmethod
    async def get_messages(conversation_id: str, limit: int = 50) -> list[dict]:
        """Get messages for a conversation, oldest first, with optional limit."""
        db = await get_db()
        async with db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
            (conversation_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["sources"] = json.loads(d["sources"]) if d["sources"] else []
                result.append(d)
            return result

    @staticmethod
    async def get_recent_messages(conversation_id: str, limit: int = 10) -> list[dict]:
        """Get the most recent messages (for LLM context)."""
        db = await get_db()
        async with db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            # Reverse to get chronological order
            result = []
            for r in reversed(rows):
                d = dict(r)
                d["sources"] = json.loads(d["sources"]) if d["sources"] else []
                result.append(d)
            return result

    @staticmethod
    async def delete_messages(conversation_id: str) -> None:
        """Delete all messages in a conversation."""
        db = await get_db()
        await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        await db.commit()
