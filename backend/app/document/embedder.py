from __future__ import annotations

import asyncio
import logging

from langchain_community.embeddings import ZhipuAIEmbeddings

from app.config import settings

logger = logging.getLogger(__name__)

_embedder: ZhipuAIEmbeddings | None = None

# Limit concurrent embedding API requests to avoid rate limiting
_SEMAPHORE = asyncio.Semaphore(5)


def get_embedder() -> ZhipuAIEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = ZhipuAIEmbeddings(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            api_key=settings.zhipu_api_key,
        )
    return _embedder


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in parallel batches of 64 (ZhipuAI limit).

    Batches are processed concurrently for faster embedding during
    document upload. Each batch runs in a thread to avoid blocking.
    Concurrency is limited by a module-level Semaphore (max 5).
    """
    try:
        embedder = get_embedder()
        batch_size = 64

        # Split into batches
        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

        async def _embed_batch(batch: list[str]) -> list[list[float]]:
            async with _SEMAPHORE:
                return await asyncio.to_thread(embedder.embed_documents, batch)

        # Run all batches in parallel (semaphore limits concurrency)
        results = await asyncio.gather(*[_embed_batch(b) for b in batches])

        all_embeddings = []
        for batch_result in results:
            all_embeddings.extend(batch_result)
        return all_embeddings
    except Exception:
        logger.exception("Embedding 失败: count=%d", len(texts))
        raise


async def embed_query(text: str) -> list[float]:
    """Embed a single query text."""
    embedder = get_embedder()
    return await asyncio.to_thread(embedder.embed_query, text)
