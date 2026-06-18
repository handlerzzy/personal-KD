"""User repository for SQLite persistence."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from app.persistence.database import get_db

logger = logging.getLogger(__name__)

# Workaround for Python 3.12 — sqlite3.IntegrityError is not importable from aiosqlite directly
try:
    from sqlite3 import IntegrityError as SQLiteIntegrityError
except ImportError:
    SQLiteIntegrityError = Exception  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for user CRUD operations."""

    @staticmethod
    async def create(username: str, hashed_password: str, email: str | None = None) -> dict:
        """Create a new user."""
        db = await get_db()
        user_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        await db.execute(
            "INSERT INTO users (id, username, hashed_password, email,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, hashed_password, email, now, now),
        )
        await db.commit()

        logger.info("User created: id=%s, username=%s", user_id, username)
        return {
            "id": user_id,
            "username": username,
            "email": email,
            "is_active": 1,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    async def get(user_id: str) -> dict | None:
        """Get user by ID."""
        db = await get_db()
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
        return None

    @staticmethod
    async def get_by_username(username: str) -> dict | None:
        """Get user by username."""
        db = await get_db()
        async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
        return None

    @staticmethod
    async def update(user_id: str, **kwargs) -> dict | None:
        """Update user fields."""
        db = await get_db()

        allowed_fields = {"email", "is_active"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return await UserRepository.get(user_id)

        updates["updated_at"] = datetime.now(UTC).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]

        await db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        await db.commit()

        logger.info("User updated: id=%s, fields=%s", user_id, list(updates.keys()))
        return await UserRepository.get(user_id)

    @staticmethod
    async def update_password(user_id: str, hashed_password: str) -> bool:
        """Update user password and increment token_version to invalidate all tokens."""
        db = await get_db()
        now = datetime.now(UTC).isoformat()

        await db.execute(
            "UPDATE users SET hashed_password = ?, token_version = token_version + 1,"
            " updated_at = ? WHERE id = ?",
            (hashed_password, now, user_id),
        )
        await db.commit()

        logger.info("Password updated for user: id=%s (token_version incremented)", user_id)
        return True

    @staticmethod
    async def delete(user_id: str) -> bool:
        """Delete user."""
        db = await get_db()
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()

        logger.info("User deleted: id=%s", user_id)
        return True

    @staticmethod
    async def list_all() -> list[dict]:
        """List all users (admin only)."""
        db = await get_db()
        async with db.execute(
            "SELECT id, username, email, is_active, created_at, updated_at FROM users"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


class TokenBlacklistRepository:
    """Repository for token blacklist operations."""

    @staticmethod
    async def add(token: str, user_id: str, expires_at: str) -> bool:
        """Add token to blacklist (idempotent — duplicate inserts are silently ignored)."""
        db = await get_db()
        token_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        try:
            await db.execute(
                "INSERT INTO token_blacklist"
                " (id, token, user_id, expires_at, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (token_id, token, user_id, expires_at, now),
            )
            await db.commit()
        except Exception:
            # UNIQUE constraint violation — token already blacklisted, ignore
            logger.debug("Token already blacklisted: user_id=%s", user_id)
            return True

        logger.info("Token blacklisted: user_id=%s", user_id)
        return True

    @staticmethod
    async def is_blacklisted(token: str) -> bool:
        """Check if token is blacklisted."""
        db = await get_db()
        async with db.execute("SELECT id FROM token_blacklist WHERE token = ?", (token,)) as cur:
            row = await cur.fetchone()
            return row is not None

    @staticmethod
    async def cleanup_expired() -> int:
        """Remove expired tokens from blacklist."""
        db = await get_db()
        now = datetime.now(UTC).isoformat()

        cursor = await db.execute("DELETE FROM token_blacklist WHERE expires_at < ?", (now,))
        deleted = cursor.rowcount
        await db.commit()

        logger.info("Cleaned up %d expired tokens", deleted)
        return deleted
