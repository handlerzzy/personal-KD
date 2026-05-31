from __future__ import annotations

import torch

from app.config import settings

_model = None
_device = None


def _get_device() -> str:
    global _device
    if _device is None:
        _device = "cuda" if torch.cuda.is_available() else "cpu"
    return _device


def get_model():
    global _model
    if _model is None:
        import logging

        from transformers import AutoModel
        logger = logging.getLogger(__name__)
        logger.info("Loading Jina Reranker v3 from %s", settings.reranker_model_path)
        _model = AutoModel.from_pretrained(
            settings.reranker_model_path,
            torch_dtype=torch.float16 if _get_device() == "cuda" else "auto",
            device_map=_get_device(),
            trust_remote_code=True,
        )
        _model.eval()
        logger.info("Reranker loaded on %s", _get_device())
    return _model


async def rerank(
    query: str,
    documents: list[dict],
    top_n: int = 5,
) -> list[dict]:
    """Re-rank documents using Jina Reranker v3."""
    if not documents:
        return []

    model = get_model()
    texts = [doc["text"] for doc in documents]

    import asyncio
    loop = asyncio.get_event_loop()

    def _run_rerank():
        results = model.rerank(query, texts, top_n=top_n)
        return results

    try:
        reranked = await loop.run_in_executor(None, _run_rerank)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Reranker failed: %s, falling back to input order", e)
        return documents[:top_n]

    # Map back to original document data
    result = []
    for item in reranked:
        idx = item.get("index")
        if idx is not None and idx < len(documents):
            doc = dict(documents[idx])
            doc["rerank_score"] = item.get("relevance_score", 0.0)
            doc["score"] = doc.get("rerank_score", doc.get("score", 0.0))
            result.append(doc)

    return result
