"""
Shared answer cleaner — strips internal pipeline metadata from LLM output.

Both ``qa_node`` (state-level) and ``chat.py`` (SSE streaming) need the same
post-processing to remove JSON metadata, document grades, verification scores,
and citation references that the LLM sometimes leaks into its response.

Single source of truth — import this function wherever stripping is needed.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def strip_answer(text: str) -> str:
    """Strip internal pipeline data from LLM answer before sending to user.

    Removes:
    - JSON metadata blocks (query_type, classification)
    - Document grade lines (文档1: relevant/irrelevant)
    - Verification score JSON blocks (faithfulness_score, etc.)
    - Suggestion fragments
    - Citation references like [1], [2], [10]
    - Partial "文档仅识别" fallback fragments
    - Excessive whitespace
    """
    if not text:
        return text

    # 1. Remove leading JSON objects containing query_type (complete or partial)
    text = re.sub(r'^\s*\{[^{}]*"query_type"[^{}]*\}?\s*', "", text)

    # 2. Remove document grade lines: "文档1: relevant", "文档2: irrelevant", etc.
    text = re.sub(r"(?:\s*文档\d+:\s*(?:relevant|irrelevant))+", "", text)

    # 3. Remove verification score JSON blocks (faithfulness_score, completeness_score, etc.)
    text = re.sub(r'\s*\{[^{}]*"faithfulness_score"[^{}]*\}', "", text)

    # 4. Remove "suggestion": "..." fragments (handles both English/Chinese colons)
    text = re.sub(r'"?suggestion"?\s*[:：]\s*"[^"]*"', "", text)

    # 5. Remove citation references like [1], [2], [10]
    #    Preserve when Chinese on BOTH sides (e.g. "第[3]步")
    #    Remove at: line end, after punctuation/spaces, consecutive, or text start
    text = re.sub(
        r"\[\d+\](?=\s*$)|\[\d+\](?=[，。！？；：、\s])|(?<![^\x00-\x7f])\[\d+\]|(?<=\])\[\d+\]",
        "",
        text,
    )

    # 6. Remove "根据现有文档无法回答" repeated fragments with grades
    text = re.sub(r"根据现有文档无法回答\.?\s*文档仅识别.*?(?=\n\n|\Z)", "", text, flags=re.DOTALL)

    # 7. Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return text
