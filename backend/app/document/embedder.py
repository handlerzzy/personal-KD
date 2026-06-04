from __future__ import annotations

import logging

from langchain_community.embeddings import ZhipuAIEmbeddings

from app.config import settings

logger = logging.getLogger(__name__)

_embedder: ZhipuAIEmbeddings | None = None


_PROXY_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "SOCKS_PROXY", "socks_proxy",
)


def get_embedder() -> ZhipuAIEmbeddings:
    global _embedder
    if _embedder is None:
        # 临时清除代理变量，避免智谱 SDK 不支持 SOCKS 代理
        import os
        saved = {k: os.environ.pop(k) for k in _PROXY_KEYS if k in os.environ}
        try:
            _embedder = ZhipuAIEmbeddings(
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                api_key=settings.zhipu_api_key,
            )
        finally:
            os.environ.update(saved)
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
