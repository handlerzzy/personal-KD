from __future__ import annotations

import asyncio
import logging

from qdrant_client import AsyncQdrantClient, QdrantClient, models

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncQdrantClient | None = None
_sync_client: QdrantClient | None = None
_use_memory: bool = False


_PROXY_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "SOCKS_PROXY", "socks_proxy",
)


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        import os
        # 临时清除代理变量，避免 SOCKS 代理导致 Qdrant 连接失败
        saved = {k: os.environ.pop(k) for k in _PROXY_KEYS if k in os.environ}
        try:
            _client = AsyncQdrantClient(url=settings.qdrant_url)
        finally:
            os.environ.update(saved)
    return _client


def get_sync_client() -> QdrantClient:
    """Get sync client for in-memory mode."""
    global _sync_client
    if _sync_client is None:
        _sync_client = QdrantClient(":memory:")
    return _sync_client


async def _check_server() -> bool:
    """Check if Qdrant server is available."""
    try:
        client = get_client()
        await client.get_collections()
        return True
    except Exception:
        return False


def _collection_name(kb_id: str) -> str:
    return f"kb_{kb_id}"


async def create_collection(kb_id: str) -> bool:
    global _use_memory
    name = _collection_name(kb_id)

    # Try server first
    if not _use_memory:
        try:
            client = get_client()
            exists = await client.collection_exists(name)
            if exists:
                return True
            return await client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=settings.embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception:
            logger.warning("Qdrant server not available, switching to in-memory mode")
            _use_memory = True

    # In-memory mode
    sync_client = get_sync_client()
    try:
        sync_client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=settings.embedding_dimensions,
                distance=models.Distance.COSINE,
            ),
        )
        return True
    except Exception:
        # Collection might already exist
        return True


async def delete_collection(kb_id: str) -> bool:
    global _use_memory
    name = _collection_name(kb_id)

    if not _use_memory:
        try:
            client = get_client()
            exists = await client.collection_exists(name)
            if not exists:
                return True
            return await client.delete_collection(name)
        except Exception:
            _use_memory = True

    # In-memory mode
    sync_client = get_sync_client()
    try:
        sync_client.delete_collection(name)
    except Exception:
        pass
    return True


async def upsert_chunks(
    kb_id: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    """Upsert document chunks into Qdrant."""
    global _use_memory
    name = _collection_name(kb_id)
    points = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        points.append(models.PointStruct(
            id=hash(chunk["chunk_id"]) % (2**63),
            vector=emb,
            payload={
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "kb_id": chunk["metadata"]["kb_id"],
                "doc_id": chunk["metadata"]["doc_id"],
                "chunk_index": chunk["metadata"]["chunk_index"],
            },
        ))

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        if not _use_memory:
            try:
                client = get_client()
                await client.upsert(name, points=batch)
            except Exception:
                logger.warning("Qdrant server not available, switching to in-memory mode")
                _use_memory = True
                sync_client = get_sync_client()
                sync_client.upsert(name, points=batch)
        else:
            sync_client = get_sync_client()
            sync_client.upsert(name, points=batch)


async def search(
    query_embedding: list[float],
    kb_id: str,
    k: int = 20,
) -> list[dict]:
    """Search Qdrant for similar vectors."""
    global _use_memory
    name = _collection_name(kb_id)

    if not _use_memory:
        try:
            client = get_client()
            exists = await client.collection_exists(name)
            if not exists:
                return []
            result = await client.query_points(
                collection_name=name,
                query=query_embedding,
                limit=k,
                with_payload=True,
            )
            return [
                {
                    "chunk_id": hit.payload.get("chunk_id", ""),
                    "text": hit.payload.get("text", ""),
                    "score": hit.score,
                    "doc_id": hit.payload.get("doc_id", ""),
                    "kb_id": hit.payload.get("kb_id", ""),
                }
                for hit in result.points
            ]
        except Exception:
            logger.warning("Qdrant server not available, switching to in-memory mode")
            _use_memory = True

    # In-memory mode
    sync_client = get_sync_client()
    try:
        result = sync_client.query_points(
            collection_name=name,
            query=query_embedding,
            limit=k,
            with_payload=True,
        )
        return [
            {
                "chunk_id": hit.payload.get("chunk_id", ""),
                "text": hit.payload.get("text", ""),
                "score": hit.score,
                "doc_id": hit.payload.get("doc_id", ""),
                "kb_id": hit.payload.get("kb_id", ""),
            }
            for hit in result.points
        ]
    except Exception as e:
        logger.warning("In-memory search failed: %s", e)
        return []


async def delete_document_chunks(kb_id: str, doc_id: str) -> None:
    """Delete all chunks belonging to a specific document."""
    global _use_memory
    name = _collection_name(kb_id)

    if not _use_memory:
        try:
            client = get_client()
            exists = await client.collection_exists(name)
            if not exists:
                return
            from qdrant_client.models import FieldCondition, Filter, MatchValue
            records, _ = await client.scroll(
                collection_name=name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=10000,
                with_payload=False,
            )
            if records:
                point_ids = [p.id for p in records]
                await client.delete(name, points_selector=models.PointIdsList(point_ids))
            return
        except Exception:
            _use_memory = True

    # In-memory mode
    sync_client = get_sync_client()
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        records, _ = sync_client.scroll(
            collection_name=name,
            scroll_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
            limit=10000,
            with_payload=False,
        )
        if records:
            point_ids = [p.id for p in records]
            sync_client.delete(name, points_selector=models.PointIdsList(point_ids))
    except Exception as e:
        logger.warning("In-memory delete failed: %s", e)
