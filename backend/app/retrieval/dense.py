from __future__ import annotations

from qdrant_client import AsyncQdrantClient, models

from app.config import settings

_client: AsyncQdrantClient | None = None


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=settings.qdrant_url)
    return _client


def _collection_name(kb_id: str) -> str:
    return f"kb_{kb_id}"


async def create_collection(kb_id: str) -> bool:
    client = get_client()
    name = _collection_name(kb_id)
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


async def delete_collection(kb_id: str) -> bool:
    client = get_client()
    name = _collection_name(kb_id)
    exists = await client.collection_exists(name)
    if not exists:
        return True
    return await client.delete_collection(name)


async def upsert_chunks(
    kb_id: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    """Upsert document chunks into Qdrant."""
    client = get_client()
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
        await client.upsert(name, points=points[i:i + batch_size])


async def search(
    query_embedding: list[float],
    kb_id: str,
    k: int = 20,
) -> list[dict]:
    """Search Qdrant for similar vectors."""
    client = get_client()
    name = _collection_name(kb_id)
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


async def delete_document_chunks(kb_id: str, doc_id: str) -> None:
    """Delete all chunks belonging to a specific document."""
    client = get_client()
    name = _collection_name(kb_id)
    exists = await client.collection_exists(name)
    if not exists:
        return

    # Scroll through all points and delete matching ones
    # Use filter to find points with matching doc_id
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
        await client.delete(name, points_selector=models.PointIdsList(points=point_ids))
