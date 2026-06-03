from __future__ import annotations

import logging

from langchain_community.embeddings import ZhipuAIEmbeddings

from app.config import settings

logger = logging.getLogger(__name__)

_embedder: ZhipuAIEmbeddings | None = None


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
    """Embed multiple texts in batches of 64 (ZhipuAI limit)."""
    try:
        embedder = get_embedder()
        import asyncio
        batch_size = 64
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            result = await asyncio.to_thread(embedder.embed_documents, batch)
            all_embeddings.extend(result)
        return all_embeddings
    except Exception:
        logger.exception("Embedding 失败: count=%d", len(texts))
        raise



async def embed_query(text: str) -> list[float]:
    """Embed a single query text."""
    embedder = get_embedder()
    import asyncio
    return await asyncio.to_thread(embedder.embed_query, text)
