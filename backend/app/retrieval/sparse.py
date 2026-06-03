from __future__ import annotations

import logging
from pathlib import Path

from app.config import BM25_DIR

logger = logging.getLogger(__name__)


def _index_path(kb_id: str) -> str:
    path = BM25_DIR / kb_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def create_index(kb_id: str) -> None:
    """Create a new BM25 index for a knowledge base."""
    from bm25x import BM25
    BM25(_index_path(kb_id), b=0.75, k1=1.2)


def delete_index(kb_id: str) -> None:
    """Delete BM25 index for a knowledge base."""
    import shutil
    path = BM25_DIR / kb_id
    if path.exists():
        shutil.rmtree(path)


def add_documents(kb_id: str, texts: list[str]) -> None:
    """Add documents to BM25 index."""
    try:
        from bm25x import BM25
        index = BM25(_index_path(kb_id))
        index.add(texts)
    except Exception:
        logger.exception("BM25 添加文档失败: kb_id=%s, count=%d", kb_id, len(texts))
        raise


def search(query: str, kb_id: str, k: int = 20) -> list[tuple]:
    """Search BM25 index."""
    from bm25x import BM25
    index_path = _index_path(kb_id)
    if not Path(index_path).exists() or not any(Path(index_path).iterdir()):
        return []
    index = BM25(index_path)
    return index.search(query, k=k)
