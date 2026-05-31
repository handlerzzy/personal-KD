from __future__ import annotations

from langchain_community.embeddings import ZhipuAIEmbeddings

from app.config import settings

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
    """Embed multiple texts."""
    embedder = get_embedder()
    # ZhipuAIEmbeddings.embed_documents is sync, run in thread pool
    import asyncio
    return await asyncio.to_thread(embedder.embed_documents, texts)


async def embed_query(text: str) -> list[float]:
    """Embed a single query text."""
    embedder = get_embedder()
    import asyncio
    return await asyncio.to_thread(embedder.embed_query, text)
