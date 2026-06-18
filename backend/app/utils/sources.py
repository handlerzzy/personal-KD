"""Shared source-building utility for RAG results.

Extracted from duplicate implementations in ``app.api.chat`` and
``app.agent.nodes.qa_node``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import KB_DIR

logger = logging.getLogger(__name__)


def build_sources(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format retrieved docs into a sources payload.

    Looks up document filename from the JSON metadata file, and includes
    the chunk's heading (section title) for context.

    Handles two doc formats:
    - From retrieval node: ``doc_id`` at top level, ``kb_id`` in metadata or top level
    - From QA node: ``doc_id`` at top level, ``kb_id`` in metadata or top level
    """
    _doc_cache: dict[str, str] = {}

    result: list[dict[str, Any]] = []
    for d in docs:
        doc_id = d.get("doc_id", "")
        kb_id = d.get("metadata", {}).get("kb_id", "") or d.get("kb_id", "")
        heading = d.get("metadata", {}).get("heading", "") or ""

        # Look up document filename
        filename = ""
        cache_key = f"{kb_id}/{doc_id}"
        if cache_key in _doc_cache:
            filename = _doc_cache[cache_key]
        elif kb_id and doc_id:
            doc_path = KB_DIR / kb_id / "documents" / f"{doc_id}.json"
            if doc_path.exists():
                try:
                    doc_data = json.loads(doc_path.read_text(encoding="utf-8"))
                    filename = doc_data.get("filename", "")
                except Exception:
                    pass
            _doc_cache[cache_key] = filename

        result.append(
            {
                "chunk_id": d.get("chunk_id", ""),
                "text": d.get("text", "")[:200],
                "score": round(d.get("score", 0.0), 4),
                "doc_id": doc_id,
                "filename": filename,
                "heading": heading,
            }
        )
    return result
