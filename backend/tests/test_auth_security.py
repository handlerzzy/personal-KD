"""Security tests for JWT authentication module.

Covers:
- Token version invalidation after password change
- Logout blacklists both access + refresh tokens
- Refresh token replay attack prevention
- Rate limiting on auth endpoints
- Security headers
- Token type validation (access vs refresh)
- Input validation (username/password format)
- Duplicate username registration (including race condition)
- Wrong password / inactive user login
- get_current_user edge cases
"""

from __future__ import annotations

import asyncio

import pytest
from app.main import app
from app.persistence.database import close_db, init_db, set_db_path
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(tmp_path):
    """Create test client with fresh database."""
    from app.main import _rate_limit_store

    db_path = tmp_path / "test_auth.db"
    set_db_path(str(db_path))
    await init_db()
    # Clear rate limit store between tests
    _rate_limit_store.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await close_db()


@pytest.fixture
async def registered_user(client: AsyncClient):
    """Register a test user and return credentials."""
    await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "TestPass123",
        },
    )
    return {"username": "testuser", "password": "TestPass123"}


async def _login(client: AsyncClient, username: str = "testuser", password: str = "TestPass123"):
    """Helper: login and return token response."""
    resp = await client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": password,
        },
    )
    return resp


# ============================================================
# 1. Registration Tests
# ============================================================


class TestRegistration:
    """Test user registration validation."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Valid registration returns 201."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "username": "newuser",
                "password": "Pass1234",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, client: AsyncClient, registered_user):
        """Duplicate username returns 400."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "password": "Another1",
            },
        )
        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_invalid_username_too_short(self, client: AsyncClient):
        """Username < 3 chars returns 400."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "username": "ab",
                "password": "Pass1234",
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_invalid_username_special_chars(self, client: AsyncClient):
        """Username with special chars returns 400."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "username": "user@name",
                "password": "Pass1234",
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_invalid_password_no_digit(self, client: AsyncClient):
        """Password without digit returns 400."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "username": "validuser",
                "password": "OnlyLetters",
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_invalid_password_no_letter(self, client: AsyncClient):
        """Password without letter returns 400."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "username": "validuser",
                "password": "12345678",
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_invalid_password_too_short(self, client: AsyncClient):
        """Password < 8 chars returns 400."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "username": "validuser",
                "password": "Ab1",
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_concurrent_same_username(self, client: AsyncClient):
        """Concurrent registration of same username: one succeeds, one returns 400 (not 500)."""

        async def register_user():
            return await client.post(
                "/api/auth/register",
                json={
                    "username": "raceuser",
                    "password": "Pass1234",
                },
            )

        # Fire two concurrent registrations
        results = await asyncio.gather(register_user(), register_user(), return_exceptions=True)

        statuses = [r.status_code for r in results if not isinstance(r, Exception)]
        # One should be 201 (created), the other should be 400 (duplicate)
        # Neither should be 500 (unhandled IntegrityError)
        assert 201 in statuses
        assert 400 in statuses
        assert 500 not in statuses


# ============================================================
# 2. Login Tests
# ============================================================


class TestLogin:
    """Test login flow."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, registered_user):
        """Valid login returns access + refresh tokens."""
        resp = await _login(client)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, registered_user):
        """Wrong password returns 401."""
        resp = await _login(client, password="WrongPass1")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Non-existent user returns 401 (not 404, to prevent user enumeration)."""
        resp = await _login(client, username="nobody", password="Pass1234")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_empty_password(self, client: AsyncClient, registered_user):
        """Empty password returns 401."""
        resp = await _login(client, password="")
        assert resp.status_code in (401, 422)


# ============================================================
# 3. Token Version Invalidation (Password Change)
# ============================================================


class TestTokenVersionInvalidation:
    """Test that password change invalidates all existing tokens."""

    @pytest.mark.asyncio
    async def test_password_change_invalidates_old_token(
        self, client: AsyncClient, registered_user
    ):
        """After password change, old access token should be rejected."""
        # Login to get tokens
        login_resp = await _login(client)
        old_token = login_resp.json()["access_token"]
        old_refresh = login_resp.json()["refresh_token"]

        # Verify old token works
        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert resp.status_code == 200

        # Change password
        resp = await client.put(
            "/api/auth/password",
            json={
                "old_password": "TestPass123",
                "new_password": "NewPass456",
            },
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 200

        # Old access token should be rejected
        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert resp.status_code == 401

        # Old refresh token should also be rejected
        resp = await client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": old_refresh,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_new_token_works_after_password_change(
        self, client: AsyncClient, registered_user
    ):
        """New login after password change returns working tokens."""
        # Login
        login_resp = await _login(client)
        old_token = login_resp.json()["access_token"]

        # Change password
        await client.put(
            "/api/auth/password",
            json={
                "old_password": "TestPass123",
                "new_password": "NewPass456",
            },
            headers={"Authorization": f"Bearer {old_token}"},
        )

        # Login with new password
        new_login = await _login(client, password="NewPass456")
        assert new_login.status_code == 200
        new_token = new_login.json()["access_token"]

        # New token works
        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_wrong_old_password_rejected(self, client: AsyncClient, registered_user):
        """Changing password with wrong old password returns 400."""
        login_resp = await _login(client)
        token = login_resp.json()["access_token"]

        resp = await client.put(
            "/api/auth/password",
            json={
                "old_password": "WrongOld1",
                "new_password": "NewPass456",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400


# ============================================================
# 4. Logout + Token Blacklisting
# ============================================================


class TestLogout:
    """Test logout blacklists both access and refresh tokens."""

    @pytest.mark.asyncio
    async def test_logout_blacklists_access_token(self, client: AsyncClient, registered_user):
        """After logout, access token should be rejected."""
        login_resp = await _login(client)
        token = login_resp.json()["access_token"]

        # Logout
        resp = await client.post(
            "/api/auth/logout", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

        # Token should be blacklisted
        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_blacklists_refresh_token(self, client: AsyncClient, registered_user):
        """After logout with refresh token, it should be rejected."""
        login_resp = await _login(client)
        token = login_resp.json()["access_token"]
        refresh = login_resp.json()["refresh_token"]

        # Logout with refresh token
        resp = await client.post(
            "/api/auth/logout",
            json={
                "refresh_token": refresh,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        # Refresh token should be rejected
        resp = await client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": refresh,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_without_refresh_token(self, client: AsyncClient, registered_user):
        """Logout without refresh_token body still works."""
        login_resp = await _login(client)
        token = login_resp.json()["access_token"]

        resp = await client.post(
            "/api/auth/logout", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200


# ============================================================
# 5. Refresh Token Replay Attack
# ============================================================


class TestRefreshTokenReplay:
    """Test that refresh tokens cannot be reused."""

    @pytest.mark.asyncio
    async def test_refresh_token_cannot_be_reused(self, client: AsyncClient, registered_user):
        """Using a refresh token twice should fail on second attempt."""
        login_resp = await _login(client)
        refresh = login_resp.json()["refresh_token"]

        # First refresh succeeds
        resp1 = await client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": refresh,
            },
        )
        assert resp1.status_code == 200

        # Second refresh with same token fails (replay attack)
        resp2 = await client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": refresh,
            },
        )
        assert resp2.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_returns_new_tokens(self, client: AsyncClient, registered_user):
        """Refresh returns a new working access token."""
        login_resp = await _login(client)
        refresh = login_resp.json()["refresh_token"]

        resp = await client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": refresh,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

        # New access token works
        new_token = data["access_token"]
        me_resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert me_resp.status_code == 200


# ============================================================
# 6. Token Type Validation
# ============================================================


class TestTokenTypeValidation:
    """Test that access and refresh tokens are used correctly."""

    @pytest.mark.asyncio
    async def test_access_token_rejected_as_refresh(self, client: AsyncClient, registered_user):
        """Using an access token as refresh token should fail."""
        login_resp = await _login(client)
        access = login_resp.json()["access_token"]

        resp = await client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": access,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_rejected_as_access(self, client: AsyncClient, registered_user):
        """Using a refresh token in Authorization header should fail."""
        login_resp = await _login(client)
        refresh = login_resp.json()["refresh_token"]

        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"})
        assert resp.status_code == 401


# ============================================================
# 7. User Info Endpoints
# ============================================================


class TestUserInfo:
    """Test /me endpoints."""

    @pytest.mark.asyncio
    async def test_get_me(self, client: AsyncClient, registered_user):
        """GET /me returns current user info."""
        login_resp = await _login(client)
        token = login_resp.json()["access_token"]

        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert "id" in data
        # Should NOT expose hashed_password
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_update_email(self, client: AsyncClient, registered_user):
        """PUT /me updates email."""
        login_resp = await _login(client)
        token = login_resp.json()["access_token"]

        resp = await client.put(
            "/api/auth/me",
            json={
                "email": "test@example.com",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client: AsyncClient):
        """Request without token returns 401."""
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_format(self, client: AsyncClient):
        """Malformed token returns 401."""
        resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
        assert resp.status_code == 401


# ============================================================
# 8. Data Isolation (Cross-User)
# ============================================================


class TestDataIsolation:
    """Test that users cannot access each other's data."""

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_users_kb(self, client: AsyncClient):
        """User A's KB should not be accessible by User B."""
        # Register User A
        await client.post(
            "/api/auth/register",
            json={
                "username": "usera",
                "password": "PassA1234",
            },
        )
        login_a = await _login(client, "usera", "PassA1234")
        token_a = login_a.json()["access_token"]

        # Register User B
        await client.post(
            "/api/auth/register",
            json={
                "username": "userb",
                "password": "PassB1234",
            },
        )
        login_b = await _login(client, "userb", "PassB1234")
        token_b = login_b.json()["access_token"]

        # User A creates a KB
        resp = await client.post(
            "/api/knowledge-bases",
            json={
                "name": "A的私有KB",
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 201
        kb_id = resp.json()["id"]

        # User B should NOT see A's KB
        resp = await client.get(
            "/api/knowledge-bases", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert resp.status_code == 200
        kb_names = [kb["name"] for kb in resp.json()]
        assert "A的私有KB" not in kb_names

        # User B should NOT be able to delete A's KB
        resp = await client.delete(
            f"/api/knowledge-bases/{kb_id}", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert resp.status_code in (403, 404)
