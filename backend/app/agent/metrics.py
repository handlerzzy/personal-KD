"""Retrieval and verification metrics tracker.

Provides structured JSON logging for agent pipeline observability.
Tracks per-query-type performance data to validate configuration choices
and identify optimization opportunities.

Design principle — "config changes need evidence":
  Every parameter change (rerank_top_k, thinking budget, etc.) should be
  justified by real-world data, not intuition.  This module collects the
  data that makes those justifications possible.

Usage::

    from app.agent.metrics import get_metrics_tracker
    tracker = get_metrics_tracker()

    # After retrieval
    tracker.log_retrieval(
        query_type="factual",
        rerank_scores=[0.92, 0.88, 0.45, 0.35, 0.30],
        rerank_top_k=5,
        queried_doc_count=15,
        search_strategy={"use_hyde": False, "multi_query_count": 1},
        latency_ms=342.5,
        kb_id="abc123",
    )

    # After verification
    tracker.log_verification(
        query_type="multi_hop",
        quality_score=0.72,
        verification_type="full",
        needs_refine=True,
    )

    # After classification
    tracker.log_classification(
        query_type="factual",
        needs_retrieval=True,
        reasoning="涉及特定术语",
    )

All output goes to the "agent_metrics" logger as JSON lines for easy
parsing by log aggregation tools.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("agent_metrics")

# ---------------------------------------------------------------------------
# Score drop detection
# ---------------------------------------------------------------------------


def _compute_score_drop_k(scores: list[float], threshold: float = 0.3) -> int | None:
    """Find the first position where the relevance score drops significantly.

    Iterates through sorted scores and returns the 1-based index of the
    first chunk where the score drops by more than ``threshold`` (as a
    fraction of the previous score).  Returns ``None`` if no significant
    drop is found.

    This is the key metric for answering: "How many chunks does this
    query_type actually need?"

    Args:
        scores: Relevance scores from reranker, sorted descending.
        threshold: Fraction drop that counts as "significant" (default 0.3 = 30%).

    Returns:
        1-based index of the drop position, or None if no significant drop.
    """
    if len(scores) < 2:
        return None

    for i in range(1, len(scores)):
        if scores[i - 1] > 0 and (scores[i - 1] - scores[i]) / scores[i - 1] > threshold:
            return i + 1  # 1-based: score drops at this position (i+1)

    return None


# ---------------------------------------------------------------------------
# MetricsTracker
# ---------------------------------------------------------------------------


class MetricsTracker:
    """Singleton tracker for agent pipeline metrics.

    Writes structured JSON to the ``agent_metrics`` logger.  Designed to be
    lightweight: all computation is cheap and logging is fire-and-forget.
    """

    def log_retrieval(
        self,
        query_type: str,
        rerank_scores: list[float],
        rerank_top_k: int,
        queried_doc_count: int,
        search_strategy: dict,
        latency_ms: float,
        kb_id: str = "",
    ) -> None:
        """Log retrieval performance metrics.

        Computes ``score_drop_k`` to indicate how many of the top-k chunks
        were actually relevant — the position where scores drop sharply.

        Args:
            query_type: Classified query type (factual/analytical/...).
            rerank_scores: Reranker relevance scores, sorted descending.
            rerank_top_k: Number of chunks retained after reranking.
            queried_doc_count: Number of documents fed into the reranker.
            search_strategy: Dict with use_hyde and multi_query_count.
            latency_ms: End-to-end retrieval latency in milliseconds.
            kb_id: Knowledge base identifier.
        """
        score_drop_k = _compute_score_drop_k(rerank_scores)
        fusion_utilization = rerank_top_k / queried_doc_count if queried_doc_count else 0.0

        payload = {
            "event": "retrieval",
            "query_type": query_type,
            "rerank_top_k": rerank_top_k,
            "queried_doc_count": queried_doc_count,
            "fusion_utilization": round(fusion_utilization, 3),
            "rerank_scores": [round(s, 4) for s in rerank_scores],
            "score_drop_k": score_drop_k,
            "search_strategy": search_strategy,
            "latency_ms": round(latency_ms, 2),
            "kb_id": kb_id,
        }
        logger.info(json.dumps(payload, ensure_ascii=False))

    def log_verification(
        self,
        query_type: str,
        quality_score: float,
        verification_type: str,
        needs_refine: bool,
        kb_id: str = "",
    ) -> None:
        """Log answer verification results.

        Only called for analytical (completeness-only) and multi_hop
        (faithfulness+completeness) queries.

        Args:
            query_type: Classified query type.
            quality_score: Overall quality score (0-1).
            verification_type: "completeness" or "full".
            needs_refine: Whether refinement was triggered.
            kb_id: Knowledge base identifier.
        """
        payload = {
            "event": "verification",
            "query_type": query_type,
            "quality_score": round(quality_score, 4),
            "verification_type": verification_type,
            "needs_refine": needs_refine,
            "kb_id": kb_id,
        }
        logger.info(json.dumps(payload, ensure_ascii=False))

    def log_classification(
        self,
        query_type: str,
        needs_retrieval: bool,
        reasoning: str = "",
    ) -> None:
        """Log query classification results.

        Tracks how the classifier routes queries — useful for auditing
        classification accuracy over time.

        Args:
            query_type: Classified query type.
            needs_retrieval: Whether retrieval was triggered.
            reasoning: LLM's classification reasoning.
        """
        payload = {
            "event": "classification",
            "query_type": query_type,
            "needs_retrieval": needs_retrieval,
            "reasoning": reasoning,
        }
        logger.info(json.dumps(payload, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_tracker: MetricsTracker | None = None


def get_metrics_tracker() -> MetricsTracker:
    """Get the singleton MetricsTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = MetricsTracker()
    return _tracker
