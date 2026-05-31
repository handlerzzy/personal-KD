"""API tests for Knowledge Base Agent (R1-R6, R8)."""
import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """R4: Health check endpoint."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_knowledge_base(client: AsyncClient):
    """R1: Create a new knowledge base."""
    resp = await client.post("/api/knowledge-bases", json={
        "name": "测试知识库",
        "description": "用于测试",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试知识库"
    assert "id" in data
    return data["id"]


@pytest.mark.asyncio
async def test_list_knowledge_bases(client: AsyncClient):
    """R1: List all knowledge bases."""
    # Create one first
    await client.post("/api/knowledge-bases", json={"name": "KB1"})
    resp = await client.get("/api/knowledge-bases")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_delete_knowledge_base(client: AsyncClient):
    """R1: Delete a knowledge base."""
    resp = await client.post("/api/knowledge-bases", json={"name": "ToDelete"})
    kb_id = resp.json()["id"]
    resp = await client.delete(f"/api/knowledge-bases/{kb_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_conversation(client: AsyncClient):
    """R6: Create conversation in a knowledge base."""
    # Create KB first
    resp = await client.post("/api/knowledge-bases", json={"name": "ConvTest"})
    kb_id = resp.json()["id"]
    # Create conversation
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"title": "测试对话"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试对话"
    assert data["kb_id"] == kb_id


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient):
    """R6: List conversations in a knowledge base."""
    resp = await client.post("/api/knowledge-bases", json={"name": "ConvList"})
    kb_id = resp.json()["id"]
    resp = await client.get(f"/api/knowledge-bases/{kb_id}/conversations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_delete_conversation(client: AsyncClient):
    """R6: Delete a conversation."""
    resp = await client.post("/api/knowledge-bases", json={"name": "ConvDel"})
    kb_id = resp.json()["id"]
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"title": "待删除"},
    )
    conv_id = resp.json()["id"]
    resp = await client.delete(
        f"/api/knowledge-bases/{kb_id}/conversations/{conv_id}"
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_without_kb(client: AsyncClient):
    """R4: Chat endpoint should return 404 for non-existent KB."""
    resp = await client.post(
        "/api/knowledge-bases/nonexistent/conversations/fake/chat",
        json={"query": "你好"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_empty_query(client: AsyncClient):
    """R4: Chat endpoint should reject empty query."""
    resp = await client.post("/api/knowledge-bases", json={"name": "ChatTest"})
    kb_id = resp.json()["id"]
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"title": "Chat"},
    )
    conv_id = resp.json()["id"]
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations/{conv_id}/chat",
        json={"query": "   "},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_messages(client: AsyncClient):
    """R6: Get messages for a conversation."""
    resp = await client.post("/api/knowledge-bases", json={"name": "MsgTest"})
    kb_id = resp.json()["id"]
    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"title": "Msg"},
    )
    conv_id = resp.json()["id"]
    resp = await client.get(
        f"/api/knowledge-bases/{kb_id}/conversations/{conv_id}/messages"
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient):
    """R2: List documents for a knowledge base."""
    resp = await client.post("/api/knowledge-bases", json={"name": "DocTest"})
    kb_id = resp.json()["id"]
    resp = await client.get(f"/api/knowledge-bases/{kb_id}/documents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
