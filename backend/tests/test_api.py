"""API tests for Knowledge Base Agent (R1-R6, R8)."""

import pytest
from app.main import app
from app.persistence.database import close_db, init_db, set_db_path
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(tmp_path):
    db_path = tmp_path / "test_agent.db"
    set_db_path(str(db_path))
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await close_db()


@pytest.fixture
async def auth_headers(client: AsyncClient):
    """Create a test user and return auth headers."""
    # Register user
    await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "TestPass123",
        },
    )
    # Login
    resp = await client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "TestPass123",
        },
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """R4: Health check endpoint."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_knowledge_base(client: AsyncClient, auth_headers: dict):
    """R1: Create a new knowledge base."""
    resp = await client.post(
        "/api/knowledge-bases",
        json={
            "name": "测试知识库",
            "description": "用于测试",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试知识库"
    assert "id" in data
    return data["id"]


@pytest.mark.asyncio
async def test_list_knowledge_bases(client: AsyncClient, auth_headers: dict):
    """R1: List all knowledge bases."""
    # Create one first
    await client.post("/api/knowledge-bases", json={"name": "KB1"}, headers=auth_headers)
    resp = await client.get("/api/knowledge-bases", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_delete_knowledge_base(client: AsyncClient, auth_headers: dict):
    """R1: Delete a knowledge base."""
    resp = await client.post(
        "/api/knowledge-bases", json={"name": "ToDelete"}, headers=auth_headers
    )
    kb_id = resp.json()["id"]
    resp = await client.delete(f"/api/knowledge-bases/{kb_id}", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_conversation(client: AsyncClient, auth_headers: dict):
    """R6: Create conversation in a knowledge base."""
    # Create KB first
    resp = await client.post(
        "/api/knowledge-bases", json={"name": "ConvTest"}, headers=auth_headers
    )
    kb_id = resp.json()["id"]
    # Create conversation
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"title": "测试对话"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试对话"
    assert data["kb_id"] == kb_id


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient, auth_headers: dict):
    """R6: List conversations in a knowledge base."""
    resp = await client.post(
        "/api/knowledge-bases", json={"name": "ConvList"}, headers=auth_headers
    )
    kb_id = resp.json()["id"]
    resp = await client.get(f"/api/knowledge-bases/{kb_id}/conversations", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_delete_conversation(client: AsyncClient, auth_headers: dict):
    """R6: Delete a conversation."""
    resp = await client.post("/api/knowledge-bases", json={"name": "ConvDel"}, headers=auth_headers)
    kb_id = resp.json()["id"]
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"title": "待删除"},
        headers=auth_headers,
    )
    conv_id = resp.json()["id"]
    resp = await client.delete(
        f"/api/knowledge-bases/{kb_id}/conversations/{conv_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_without_kb(client: AsyncClient, auth_headers: dict):
    """R4: Chat endpoint should return 404 for non-existent KB."""
    resp = await client.post(
        "/api/knowledge-bases/nonexistent/conversations/fake/chat",
        json={"query": "你好"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_empty_query(client: AsyncClient, auth_headers: dict):
    """R4: Chat endpoint should reject empty query."""
    resp = await client.post(
        "/api/knowledge-bases", json={"name": "ChatTest"}, headers=auth_headers
    )
    kb_id = resp.json()["id"]
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"title": "Chat"},
        headers=auth_headers,
    )
    conv_id = resp.json()["id"]
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations/{conv_id}/chat",
        json={"query": "   "},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_messages(client: AsyncClient, auth_headers: dict):
    """R6: Get messages for a conversation."""
    resp = await client.post("/api/knowledge-bases", json={"name": "MsgTest"}, headers=auth_headers)
    kb_id = resp.json()["id"]
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"title": "Msg"},
        headers=auth_headers,
    )
    conv_id = resp.json()["id"]
    resp = await client.get(
        f"/api/knowledge-bases/{kb_id}/conversations/{conv_id}/messages",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, auth_headers: dict):
    """R2: List documents for a knowledge base."""
    resp = await client.post("/api/knowledge-bases", json={"name": "DocTest"}, headers=auth_headers)
    kb_id = resp.json()["id"]
    resp = await client.get(f"/api/knowledge-bases/{kb_id}/documents", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
