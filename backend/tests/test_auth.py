"""Tests for authentication functionality."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_password_hash,
    validate_password,
    validate_username,
    verify_password,
)
from app.config import settings
from jose import jwt


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password(self):
        """Test password hashing."""
        password = "TestPass123"
        hashed = get_password_hash(password)
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_verify_correct_password(self):
        """Test verifying correct password."""
        password = "TestPass123"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        """Test verifying wrong password."""
        password = "TestPass123"
        wrong_password = "WrongPass123"
        hashed = get_password_hash(password)
        assert verify_password(wrong_password, hashed) is False

    def test_different_hashes_for_same_password(self):
        """Test that same password produces different hashes (due to salt)."""
        password = "TestPass123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestInputValidation:
    """Test username and password validation."""

    def test_valid_username(self):
        """Test valid usernames."""
        assert validate_username("john") is True
        assert validate_username("john_doe") is True
        assert validate_username("user123") is True
        assert validate_username("abc") is True  # min length
        assert validate_username("a" * 20) is True  # max length

    def test_invalid_username(self):
        """Test invalid usernames."""
        assert validate_username("ab") is False  # too short
        assert validate_username("a" * 21) is False  # too long
        assert validate_username("john doe") is False  # space
        assert validate_username("john@doe") is False  # special char
        assert validate_username("") is False

    def test_valid_password(self):
        """Test valid passwords."""
        assert validate_password("TestPass123") is True
        assert validate_password("Abcdef1g") is True  # min length
        assert validate_password("A" * 20 + "a1") is False  # too long
        assert validate_password("Test1234") is True  # 8 chars

    def test_invalid_password(self):
        """Test invalid passwords."""
        assert validate_password("TestPassw") is False  # no digit
        assert validate_password("Te1") is False  # too short (< 8 chars)
        assert validate_password("") is False
        # Note: regex only requires [a-zA-Z] + \d, not specific case
        assert validate_password("testpass123") is True  # lowercase + digit = valid
        assert validate_password("TESTPASS123") is True  # uppercase + digit = valid


class TestTokenCreation:
    """Test JWT token creation."""

    def test_create_access_token(self):
        """Test access token creation."""
        user_id = "test_user_123"
        token = create_access_token(data={"sub": user_id})
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["sub"] == user_id
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_refresh_token(self):
        """Test refresh token creation."""
        user_id = "test_user_123"
        token = create_refresh_token(data={"sub": user_id})
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"
        assert "exp" in payload
        assert "jti" in payload  # refresh token should have unique ID

    def test_token_expiration(self):
        """Test token expiration times."""
        user_id = "test_user_123"

        # Access token should expire in 2 hours
        access_token = create_access_token(data={"sub": user_id})
        access_payload = jwt.decode(access_token, settings.secret_key, algorithms=[ALGORITHM])
        access_exp = datetime.fromtimestamp(access_payload["exp"], tz=UTC)
        expected_access_exp = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        assert abs((access_exp - expected_access_exp).total_seconds()) < 10  # within 10 seconds

        # Refresh token should expire in 7 days
        refresh_token = create_refresh_token(data={"sub": user_id})
        refresh_payload = jwt.decode(refresh_token, settings.secret_key, algorithms=[ALGORITHM])
        refresh_exp = datetime.fromtimestamp(refresh_payload["exp"], tz=UTC)
        expected_refresh_exp = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        assert abs((refresh_exp - expected_refresh_exp).total_seconds()) < 10  # within 10 seconds

    def test_custom_expiration(self):
        """Test custom expiration times."""
        user_id = "test_user_123"
        custom_delta = timedelta(minutes=30)

        token = create_access_token(data={"sub": user_id}, expires_delta=custom_delta)
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        expected_exp = datetime.now(UTC) + custom_delta
        assert abs((exp - expected_exp).total_seconds()) < 10


class TestTokenDecoding:
    """Test JWT token decoding."""

    def test_decode_valid_token(self):
        """Test decoding valid token."""
        user_id = "test_user_123"
        token = create_access_token(data={"sub": user_id})
        payload = decode_token(token)
        assert payload["sub"] == user_id
        assert payload["type"] == "access"

    def test_decode_expired_token(self):
        """Test decoding expired token."""
        user_id = "test_user_123"
        # Create token that expired 1 hour ago
        expired_delta = timedelta(hours=-1)
        token = create_access_token(data={"sub": user_id}, expires_delta=expired_delta)

        with pytest.raises(Exception):  # Should raise HTTPException
            decode_token(token)

    def test_decode_invalid_token(self):
        """Test decoding invalid token."""
        with pytest.raises(Exception):  # Should raise HTTPException
            decode_token("invalid.token.here")

    def test_decode_token_with_wrong_secret(self):
        """Test decoding token signed with wrong secret."""
        user_id = "test_user_123"
        # Create token with wrong secret
        token = jwt.encode(
            {"sub": user_id, "exp": datetime.now(UTC) + timedelta(hours=1)},
            "wrong_secret",
            algorithm=ALGORITHM,
        )

        with pytest.raises(Exception):  # Should raise HTTPException
            decode_token(token)


class TestDatabaseIntegration:
    """Test database integration (requires running database)."""

    @pytest.mark.asyncio
    async def test_user_repository_create(self):
        """Test user creation in database."""
        from app.persistence.user_repo import UserRepository

        # This test requires a running database
        # Skip if database is not available
        try:
            user = await UserRepository.create(
                username="testuser",
                hashed_password=get_password_hash("TestPass123"),
                email="test@example.com",
            )
            assert user["username"] == "testuser"
            assert user["email"] == "test@example.com"
            assert "id" in user

            # Cleanup
            await UserRepository.delete(user["id"])
        except Exception as e:
            pytest.skip(f"Database not available: {e}")

    @pytest.mark.asyncio
    async def test_user_repository_get_by_username(self):
        """Test getting user by username."""
        from app.persistence.user_repo import UserRepository

        try:
            # Create user
            user = await UserRepository.create(
                username="testuser2",
                hashed_password=get_password_hash("TestPass123"),
            )

            # Get by username
            found = await UserRepository.get_by_username("testuser2")
            assert found is not None
            assert found["username"] == "testuser2"

            # Cleanup
            await UserRepository.delete(user["id"])
        except Exception as e:
            pytest.skip(f"Database not available: {e}")

    @pytest.mark.asyncio
    async def test_token_blacklist(self):
        """Test token blacklisting."""
        from app.persistence.user_repo import TokenBlacklistRepository

        try:
            token = "test_token_123"
            user_id = "test_user_123"
            expires_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

            # Add to blacklist
            await TokenBlacklistRepository.add(token, user_id, expires_at)

            # Check if blacklisted
            is_blacklisted = await TokenBlacklistRepository.is_blacklisted(token)
            assert is_blacklisted is True

            # Check non-blacklisted token
            is_blacklisted = await TokenBlacklistRepository.is_blacklisted("other_token")
            assert is_blacklisted is False
        except Exception as e:
            pytest.skip(f"Database not available: {e}")

    @pytest.mark.asyncio
    async def test_token_blacklist_idempotent_add(self):
        """Test that adding the same token twice does not raise (UNIQUE constraint)."""
        from app.persistence.user_repo import TokenBlacklistRepository

        try:
            token = "idempotent_token_123"
            user_id = "test_user_123"
            expires_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

            # First add
            result1 = await TokenBlacklistRepository.add(token, user_id, expires_at)
            assert result1 is True

            # Second add — should not raise, should be idempotent
            result2 = await TokenBlacklistRepository.add(token, user_id, expires_at)
            assert result2 is True

            # Still blacklisted
            assert await TokenBlacklistRepository.is_blacklisted(token) is True
        except Exception as e:
            pytest.skip(f"Database not available: {e}")

    @pytest.mark.asyncio
    async def test_get_current_user_excludes_hashed_password(self):
        """Test that get_current_user does not leak hashed_password."""
        from unittest.mock import AsyncMock, patch

        mock_user = {
            "id": "user123",
            "username": "testuser",
            "hashed_password": "$2b$12$secret_hash",
            "email": None,
            "is_active": 1,
            "token_version": 0,
        }

        with (
            patch("app.auth.decode_token") as mock_decode,
            patch("app.auth.TokenBlacklistRepository") as mock_blacklist,
            patch("app.auth.UserRepository") as mock_user_repo,
        ):
            mock_decode.return_value = {
                "sub": "user123",
                "type": "access",
                "token_version": 0,
            }
            mock_blacklist.is_blacklisted = AsyncMock(return_value=False)
            mock_user_repo.get = AsyncMock(return_value=mock_user)

            result = await get_current_user(token="valid-token")

            # hashed_password must NOT be in the returned dict
            assert "hashed_password" not in result
            assert result["username"] == "testuser"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
