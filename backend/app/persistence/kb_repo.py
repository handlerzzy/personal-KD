"""Knowledge base repository — CRUD operations for KB metadata."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.persistence.database import get_db

logger = logging.getLogger(__name__)


class KbRepository:
    """Knowledge base persistence using SQLite."""

    @staticmethod
    async def create(name: str, description: str = "", user_id: str | None = None) -> dict:
        """Create a new knowledge base."""
        db = await get_db()
        kb_id = uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        await db.execute(
            "INSERT INTO knowledge_bases"
            " (id, name, description, user_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (kb_id, name, description, user_id, now, now),
        )
        await db.commit()

        logger.info("KB created: id=%s, name=%s, user_id=%s", kb_id, name, user_id)
        return {
            "id": kb_id,
            "name": name,
            "description": description,
            "doc_count": 0,
            "conv_count": 0,
            "user_id": user_id,
            "created_at": now,
        }

    @staticmethod
    async def get(kb_id: str) -> dict | None:
        """Get a knowledge base by ID."""
        db = await get_db()
        async with db.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,)) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return dict(row)

    @staticmethod
    async def list_all() -> list[dict]:
        """List all knowledge bases, newest first."""
        db = await get_db()
        async with db.execute("SELECT * FROM knowledge_bases ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    async def list_by_user(user_id: str) -> list[dict]:
        """List knowledge bases for a specific user, newest first."""
        if not user_id:
            return []

        db = await get_db()
        async with db.execute(
            "SELECT * FROM knowledge_bases WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    async def update_doc_count(kb_id: str, delta: int = 1) -> None:
        """Increment/decrement document count."""
        db = await get_db()
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE knowledge_bases SET doc_count = doc_count + ?, updated_at = ? WHERE id = ?",
            (delta, now, kb_id),
        )
        await db.commit()

    @staticmethod
    async def update_name(kb_id: str, name: str, description: str = "") -> None:
        """Update KB name and description."""
        db = await get_db()
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE knowledge_bases SET name = ?, description = ?, updated_at = ? WHERE id = ?",
            (name, description, now, kb_id),
        )
        await db.commit()

    @staticmethod
    async def update_conv_count(kb_id: str) -> None:
        """Recalculate conversation count from conversations table."""
        db = await get_db()
        async with db.execute(
            "SELECT COUNT(*) FROM conversations WHERE kb_id = ?", (kb_id,)
        ) as cur:
            count = (await cur.fetchone())[0]
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE knowledge_bases SET conv_count = ?, updated_at = ? WHERE id = ?",
            (count, now, kb_id),
        )
        await db.commit()

    @staticmethod
    async def delete(kb_id: str) -> None:
        """Delete a knowledge base (cascades to conversations and messages)."""
        db = await get_db()
        await db.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
        await db.commit()
        logger.info("KB deleted: id=%s", kb_id)
