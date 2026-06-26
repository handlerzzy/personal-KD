"""Enhanced retrieval node — supports HyDE and Multi-Query retrieval.

Retrieval flow:
1. Check search_strategy from classify_query node
2. If use_hyde: generate hypothetical answer, use its embedding for dense search
3. If multi_query_count > 1: generate query variations, merge results
4. Dense + Sparse → RRF fusion → Rerank → filtered docs
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState
from app.agent.metrics import get_metrics_tracker
from app.retrieval import dense, hybrid, sparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query-type-aware retrieval configuration
#
# Different query types need different amounts of context:
#   factual     → few chunks with tolerance (risk: missing relevant docs)
#   analytical  → moderate coverage (needs supporting evidence)
#   multi_hop   → high recall (needs cross-document connections)
#   summary     → broad coverage (needs full picture)
#
# Design principle — "LLM qualifies, code quantifies":
#   LLM (classify_query) decides the *type*.
#   Code decides the *numbers* — stable, testable, tunable.
# ---------------------------------------------------------------------------
RETRIEVAL_CONFIG: dict[str, dict] = {
    "factual": {"rerank_top_k": 5, "k_per_query": 20, "fusion_top_n": 15},
    "analytical": {"rerank_top_k": 5, "k_per_query": 30, "fusion_top_n": 30},
    "multi_hop": {"rerank_top_k": 8, "k_per_query": 30, "fusion_top_n": 30},
    "summary": {"rerank_top_k": 10, "k_per_query": 40, "fusion_top_n": 40},
    # Unknown / missing query_type → conservative medium-intensity retrieval
    "default": {"rerank_top_k": 5, "k_per_query": 30, "fusion_top_n": 30},
}

_HYDE_PROMPT = """你是一个学术助手。根据以下问题，生成一个简短的假设性答案（2-3句话）。
这个答案不需要准确，只需要包含可能出现在真实答案中的关键词和概念。

问题: {query}

假设性答案:"""

_MULTI_QUERY_PROMPT = """你是一个查询扩展专家。为以下问题生成 {n} 个不同角度的查询变体。
每个变体应从不同角度提问，但保持核心意图不变。
每行一个查询，不要编号。

原始查询: {query}

查询变体:"""


from app.llm_cache import get_dashscope_llm  # noqa: E402


def _get_llm(temperature: float = 0) -> ChatOpenAI:
    """Get DashScope qwen-flash for fast query expansion tasks."""
    return get_dashscope_llm(temperature=temperature)


# ---------------------------------------------------------------------------
# Embedding LRU cache
#
# Reduces redundant embedding API calls when multiple queries share the same
# or similar content (e.g. repeated user questions, HyDE documents that happen
# to be identical for similar queries).  LRU maxsize=128 keeps ~1 MB of float
# vectors in memory.
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=128)
def _cached_embed_query(text: str) -> list[float]:
    """Synchronous embedding wrapper with LRU cache."""
    from app.document.embedder import get_embedder

    return get_embedder().embed_query(text)


async def _embed_query_with_cache(text: str) -> list[float]:
    """Embed query text, returning cached result if available."""
    return await asyncio.to_thread(_cached_embed_query, text)


async def _generate_hyde(query: str) -> str:
    """Generate a hypothetical document for HyDE retrieval.

    Uses a higher temperature (0.7) to produce more diverse keyword coverage,
    which improves recall for HyDE-based dense retrieval.
    """
    llm = _get_llm(temperature=0.7)
    messages = [
        SystemMessage(content="你是一个学术助手，根据问题生成假设性文档片段。"),
        HumanMessage(content=_HYDE_PROMPT.format(query=query)),
    ]
    try:
        response = await llm.ainvoke(messages)
        return (response.content or "").strip()
    except Exception:
        logger.exception("HyDE generation failed")
        return query  # Fallback to original query


async def _generate_multi_queries(query: str, count: int) -> list[str]:
    """Generate multiple query variations for broader retrieval."""
    if count <= 1:
        return [query]

    llm = _get_llm(temperature=0.5)
    messages = [
        SystemMessage(content="你是一个查询扩展专家，为问题生成不同角度的查询变体。"),
        HumanMessage(content=_MULTI_QUERY_PROMPT.format(query=query, n=count - 1)),
    ]
    try:
        response = await llm.ainvoke(messages)
        raw = (response.content or "").strip()
        variants = [line.strip() for line in raw.splitlines() if line.strip()]
        # Include original query
        all_queries = [query] + variants[: count - 1]
        return all_queries
    except Exception:
        logger.exception("Multi-query generation failed")
        return [query]


async def _dense_search_with_hyde(
    query: str, kb_id: str, use_hyde: bool, k: int = 50
) -> list[dict]:
    """Dense retrieval, optionally using HyDE."""
    if use_hyde:
        hypo_doc = await _generate_hyde(query)
        q_emb = await _embed_query_with_cache(hypo_doc)
    else:
        q_emb = await _embed_query_with_cache(query)
    return await dense.search(q_emb, kb_id, k=k)


async def _multi_query_retrieve(
    queries: list[str],
    kb_id: str,
    use_hyde: bool,
    k_per_query: int = 30,
) -> tuple[list[dict], list[dict]]:
    """Retrieve with multiple query variations, merge and deduplicate results.

    Returns (dense_results, sparse_results) with deduplication.
    """
    if len(queries) <= 1:
        # Single query — standard retrieval (with optional HyDE)
        dense_results = await _dense_search_with_hyde(
            queries[0], kb_id, use_hyde=use_hyde, k=k_per_query
        )
        sparse_results = await asyncio.to_thread(sparse.search, queries[0], kb_id, k=k_per_query)
        return dense_results, sparse_results

    # Multi-query: retrieve for each variant and merge
    all_dense = []
    all_sparse = []

    # Use HyDE only for the first (original) query if enabled
    tasks_dense = []
    for i, q in enumerate(queries):
        if i == 0 and use_hyde:
            tasks_dense.append(_dense_search_with_hyde(q, kb_id, use_hyde=True, k=k_per_query))
        else:
            tasks_dense.append(_dense_search_with_hyde(q, kb_id, use_hyde=False, k=k_per_query))

    # Run all dense searches in parallel
    dense_results_list = await asyncio.gather(*tasks_dense, return_exceptions=True)
    for result in dense_results_list:
        if isinstance(result, list):
            all_dense.extend(result)

    # Run all sparse searches in parallel (using thread pool)
    sparse_tasks = [asyncio.to_thread(sparse.search, q, kb_id, k=k_per_query) for q in queries]
    sparse_results_list = await asyncio.gather(*sparse_tasks, return_exceptions=True)
    for result in sparse_results_list:
        if isinstance(result, list):
            all_sparse.extend(result)

    # Deduplicate by chunk_id (keep highest score)
    def dedup(results: list[dict]) -> list[dict]:
        seen = {}
        for doc in results:
            cid = doc.get("chunk_id", "")
            if cid not in seen or doc.get("score", 0) > seen[cid].get("score", 0):
                seen[cid] = doc
        return list(seen.values())

    return dedup(all_dense), dedup(all_sparse)


async def retrieval_node(state: AgentState) -> dict:
    """Enhanced hybrid retrieval with HyDE and Multi-Query support.

    Reads search_strategy from classify_query to determine:
    - use_hyde: use hypothetical document embedding for dense search
    - multi_query_count: number of query variations to generate

    Reads query_type from state to dynamically adjust retrieval parameters:
    - factual:   few chunks with good tolerance (rerank_top_k=5)
    - analytical: moderate coverage (rerank_top_k=5)
    - multi_hop: high recall (rerank_top_k=8)
    - summary:   broad coverage (rerank_top_k=10)
    """
    query = state["query"]
    kb_id = state["kb_id"]
    if not query or not kb_id:
        return {"retrieved_docs": [], "messages": []}

    t0 = time.perf_counter()

    # Read strategy from classify_query
    strategy = state.get("search_strategy", {})
    use_hyde = strategy.get("use_hyde", False)
    multi_query_count = strategy.get("multi_query_count", 1)

    # Dynamic parameter selection based on query_type
    qtype = state.get("query_type", "default")
    config = RETRIEVAL_CONFIG.get(qtype, RETRIEVAL_CONFIG["default"])

    # 1. Generate query variations if needed
    if multi_query_count > 1:
        queries = await _generate_multi_queries(query, multi_query_count)
    else:
        queries = [query]

    # 2. Execute retrieval (dense + sparse) with optional HyDE
    dense_results, sparse_results = await _multi_query_retrieve(
        queries,
        kb_id,
        use_hyde,
        k_per_query=config["k_per_query"],
    )

    # 3. RRF Fusion with configurable top_n
    fused = hybrid.rrf_fusion(dense_results, sparse_results, top_n=config["fusion_top_n"])

    # 4. Rerank with query-type-aware top_k
    from app.retrieval.reranker import rerank

    final_docs = await rerank(query, fused, top_n=config["rerank_top_k"])

    # Log retrieval metrics for observability
    latency_ms = (time.perf_counter() - t0) * 1000
    rerank_scores = [doc.get("rerank_score", 0.0) for doc in final_docs]
    get_metrics_tracker().log_retrieval(
        query_type=qtype,
        rerank_scores=rerank_scores,
        rerank_top_k=config["rerank_top_k"],
        queried_doc_count=len(fused),
        search_strategy=strategy,
        latency_ms=latency_ms,
        kb_id=kb_id,
    )

    return {"retrieved_docs": final_docs, "messages": []}
