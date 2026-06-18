from __future__ import annotations

import asyncio
import hashlib
import logging

from qdrant_client import AsyncQdrantClient, QdrantClient, models

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncQdrantClient | None = None
_sync_client: QdrantClient | None = None
_use_memory: bool = False


def _stable_id(chunk_id: str) -> int:
    """Generate a stable integer ID from chunk_id string using MD5."""
    return int(hashlib.md5(chunk_id.encode()).hexdigest()[:16], 16)


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=settings.qdrant_url)
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
    vectors_config = models.VectorParams(
        size=settings.embedding_dimensions,
        distance=models.Distance.COSINE,
    )

    # Try server first
    if not _use_memory:
        try:
            client = get_client()
            exists = await client.collection_exists(name)
            if exists:
                logger.info("Collection already exists: %s", name)
                return True
            result = await client.create_collection(
                collection_name=name,
                vectors_config=vectors_config,
            )
            logger.info("Created collection on server: %s", name)
            return result
        except Exception as e:
            logger.warning("Qdrant server not available (%s), switching to in-memory mode", e)
            _use_memory = True

    # In-memory mode
    try:
        sync_client = get_sync_client()
        # Check if already exists
        try:
            sync_client.get_collection(name)
            logger.info("In-memory collection already exists: %s", name)
            return True
        except Exception:
            pass
        await asyncio.to_thread(
            sync_client.create_collection,
            collection_name=name,
            vectors_config=vectors_config,
        )
        logger.info("Created in-memory collection: %s", name)
        return True
    except Exception as e:
        logger.exception("Failed to create collection %s: %s", name, e)
        return False


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
    try:
        await asyncio.to_thread(get_sync_client().delete_collection, name)
    except Exception:
        logger.debug("In-memory collection delete failed (may not exist): %s", name, exc_info=True)
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
        points.append(
            models.PointStruct(
                id=_stable_id(chunk["chunk_id"]),
                vector=emb,
                payload={
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "kb_id": chunk["metadata"]["kb_id"],
                    "doc_id": chunk["metadata"]["doc_id"],
                    "chunk_index": chunk["metadata"]["chunk_index"],
                },
            )
        )

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        if not _use_memory:
            try:
                client = get_client()
                await client.upsert(name, points=batch)
            except Exception as e:
                logger.warning("Qdrant server upsert failed (%s), switching to in-memory mode", e)
                _use_memory = True
                # Ensure collection exists in memory
                sync_client = get_sync_client()
                try:
                    sync_client.get_collection(name)
                except Exception:
                    logger.info("Creating missing in-memory collection: %s", name)
                    from qdrant_client.models import Distance, VectorParams

                    await asyncio.to_thread(
                        sync_client.create_collection,
                        collection_name=name,
                        vectors_config=VectorParams(
                            size=settings.embedding_dimensions,
                            distance=Distance.COSINE,
                        ),
                    )
                await asyncio.to_thread(sync_client.upsert, name, points=batch)
        else:
            await asyncio.to_thread(get_sync_client().upsert, name, points=batch)


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
    try:
        result = await asyncio.to_thread(
            get_sync_client().query_points,
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

            scroll_filter = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )
            offset = None
            while True:
                records, offset = await client.scroll(
                    collection_name=name,
                    scroll_filter=scroll_filter,
                    limit=10000,
                    offset=offset,
                    with_payload=False,
                )
                if records:
                    point_ids = [p.id for p in records]
                    await client.delete(name, points_selector=models.PointIdsList(point_ids))
                if offset is None:
                    break
            return
        except Exception:
            _use_memory = True

    # In-memory mode
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        scroll_filter = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        offset = None
        while True:
            results, offset = await asyncio.to_thread(
                get_sync_client().scroll,
                collection_name=name,
                scroll_filter=scroll_filter,
                limit=10000,
                offset=offset,
                with_payload=False,
            )
            if not results:
                break
            point_ids = [p.id for p in results]
            await asyncio.to_thread(
                get_sync_client().delete,
                name,
                points_selector=models.PointIdsList(point_ids),
            )
            if offset is None:
                break
    except Exception as e:
        logger.warning("In-memory delete failed: %s", e)
