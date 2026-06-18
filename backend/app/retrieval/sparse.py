from __future__ import annotations

import json
import logging
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from app.config import BM25_DIR

logger = logging.getLogger(__name__)

# Module-level BM25 index cache: kb_id -> (mtime, BM25Okapi, corpus, texts, chunk_ids)
_bm25_cache: dict[str, tuple] = {}


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text into a list of terms.

    Handles Chinese (via jieba) and English (preserved as-is) in a single
    pass, so BM25 can index and search multilingual documents correctly.
    """
    return [t.strip() for t in jieba.lcut(text) if t.strip()]


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _index_path(kb_id: str) -> str:
    """Return the BM25 index directory path for a KB."""
    path = BM25_DIR / kb_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _corpus_path(kb_id: str) -> Path:
    """Path to JSON file storing the tokenized corpus (list of token lists).

    This file serves as the persistent store for :class:`BM25Okapi` — on
    process restart the corpus is deserialised and the index is rebuilt.
    """
    return BM25_DIR / kb_id / "corpus.json"


def _texts_path(kb_id: str) -> Path:
    """Path to JSON file mapping doc index -> original chunk text.

    Each index corresponds to the same position in the tokenized corpus so
    :func:`search` can look up the original text by rank position.
    """
    return BM25_DIR / kb_id / "texts.json"


def _chunk_ids_path(kb_id: str) -> Path:
    """Path to JSON file mapping doc index -> real chunk_id.

    Each index corresponds to the same position in the tokenized corpus so
    :func:`search` can return real chunk_ids for RRF fusion with dense results.
    """
    return BM25_DIR / kb_id / "chunk_ids.json"


def _load_json(path: Path) -> list:
    """Load a list from a JSON file, returning [] if missing."""
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: list) -> None:
    """Persist a list to a JSON file, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _get_bm25_index(kb_id: str) -> tuple:
    """Get or rebuild BM25 index with mtime-based cache invalidation.

    Returns (bm25, corpus, texts, chunk_ids) or (None, [], [], []) if missing.
    """
    index_dir = BM25_DIR / kb_id
    corpus_path = index_dir / "corpus.json"
    if not corpus_path.exists():
        return None, [], [], []

    mtime = corpus_path.stat().st_mtime
    cached = _bm25_cache.get(kb_id)
    if cached and cached[0] == mtime:
        return cached[1], cached[2], cached[3], cached[4]

    # Rebuild
    corpus = _load_json(corpus_path)
    texts = _load_json(index_dir / "texts.json")
    chunk_ids = _load_json(index_dir / "chunk_ids.json")
    bm25 = BM25Okapi(corpus)
    _bm25_cache[kb_id] = (mtime, bm25, corpus, texts, chunk_ids)
    return bm25, corpus, texts, chunk_ids


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_index(kb_id: str) -> None:
    """Create a new BM25 index for a knowledge base.

    Initialises the tokenized corpus, original-text store, and chunk-id
    mapping as empty lists.  Call :func:`add_documents` to populate them.
    """
    _index_path(kb_id)  # ensure directory exists
    _save_json(_corpus_path(kb_id), [])
    _save_json(_texts_path(kb_id), [])
    _save_json(_chunk_ids_path(kb_id), [])


def delete_index(kb_id: str) -> None:
    """Delete BM25 index for a knowledge base (corpus + texts)."""
    import shutil

    path = BM25_DIR / kb_id
    if path.exists():
        shutil.rmtree(path)
    _bm25_cache.pop(kb_id, None)


def remove_documents_by_doc_id(kb_id: str, doc_id: str) -> int:
    """Remove all BM25 entries belonging to a specific document.

    Filters the tokenized corpus, texts, and chunk_ids arrays in-place,
    removing entries whose chunk_id starts with ``{doc_id}_chunk_``.

    Returns the number of entries removed.
    """
    try:
        corpus = _load_json(_corpus_path(kb_id))
        texts = _load_json(_texts_path(kb_id))
        chunk_ids = _load_json(_chunk_ids_path(kb_id))

        if not chunk_ids:
            return 0

        # Build set of indices to keep (those NOT belonging to doc_id)
        keep_indices = []
        removed = 0
        for i, cid in enumerate(chunk_ids):
            if isinstance(cid, str) and cid.startswith(f"{doc_id}_chunk_"):
                removed += 1
            else:
                keep_indices.append(i)

        if removed == 0:
            return 0

        # Filter all three parallel arrays
        new_corpus = [corpus[i] for i in keep_indices if i < len(corpus)]
        new_texts = [texts[i] for i in keep_indices if i < len(texts)]
        new_chunk_ids = [chunk_ids[i] for i in keep_indices]

        _save_json(_corpus_path(kb_id), new_corpus)
        _save_json(_texts_path(kb_id), new_texts)
        _save_json(_chunk_ids_path(kb_id), new_chunk_ids)

        # Invalidate cache
        _bm25_cache.pop(kb_id, None)

        logger.info("BM25 移除文档: kb_id=%s, doc_id=%s, removed=%d", kb_id, doc_id, removed)
        return removed
    except Exception:
        logger.exception("BM25 移除文档失败: kb_id=%s, doc_id=%s", kb_id, doc_id)
        raise


def add_documents(
    kb_id: str,
    texts: list[str],
    chunk_ids: list[str] | None = None,
) -> None:
    """Add documents to BM25 index.

    Three persistent files are maintained in ``data/bm25_indexes/{kb_id}/``:

    * ``corpus.json``    — tokenized document list for :class:`BM25Okapi`
    * ``texts.json``     — original chunk text for retrieval
    * ``chunk_ids.json`` — real chunk_id for each entry (for RRF fusion)

    The tokenized corpus, original texts, and chunk_ids share the same
    positional index, enabling :func:`search` to map BM25 rank positions
    back to source text and real chunk identifiers.
    """
    try:
        tokenized = [_tokenize(t) for t in texts]

        corpus = _load_json(_corpus_path(kb_id))
        corpus.extend(tokenized)
        _save_json(_corpus_path(kb_id), corpus)

        stored = _load_json(_texts_path(kb_id))
        stored.extend(texts)
        _save_json(_texts_path(kb_id), stored)

        if chunk_ids is not None:
            ids = _load_json(_chunk_ids_path(kb_id))
            ids.extend(chunk_ids)
            _save_json(_chunk_ids_path(kb_id), ids)

        # Invalidate cache so next search rebuilds from updated files
        _bm25_cache.pop(kb_id, None)
    except Exception:
        logger.exception("BM25 添加文档失败: kb_id=%s, count=%d", kb_id, len(texts))
        raise


def search(query: str, kb_id: str, k: int = 50) -> list[dict]:
    """Search BM25 index and return results with chunk_id, text, and score.

    Returns up to *k* documents; scores are BM25 relevancy scores.

    Return format (matching dense search for RRF fusion compatibility)::

        {"chunk_id": str, "text": str, "score": float, "doc_id": str, "kb_id": str}
    """
    bm25, corpus, texts, chunk_id_map = _get_bm25_index(kb_id)
    if bm25 is None or not corpus:
        return []

    tokenized_query = _tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    # Rank by score descending, keep top-k
    ranked = sorted(
        ((i, scores[i]) for i in range(len(scores))),
        key=lambda x: x[1],
        reverse=True,
    )[:k]

    results: list[dict] = []
    for idx, score in ranked:
        if score <= 0:
            continue

        # Derive real chunk_id and doc_id from mapping
        if idx < len(chunk_id_map) and chunk_id_map[idx]:
            real_chunk_id = chunk_id_map[idx]
            # doc_id is everything before "_chunk_"
            doc_id = real_chunk_id.rsplit("_chunk_", 1)[0] if "_chunk_" in real_chunk_id else ""
        else:
            real_chunk_id = f"bm25_{idx}"
            doc_id = ""

        results.append(
            {
                "chunk_id": real_chunk_id,
                "text": texts[idx],
                "score": float(score),
                "doc_id": doc_id,
                "kb_id": kb_id,
            }
        )
    return results
