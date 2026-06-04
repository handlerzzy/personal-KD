from __future__ import annotations

from app.agent.state import AgentState
from app.document.embedder import embed_query
from app.retrieval import dense, hybrid, sparse


async def retrieval_node(state: AgentState) -> dict:
    """Hybrid retrieval: dense + sparse -> RRF -> rerank."""
    query = state["query"]
    kb_id = state["kb_id"]
    if not query or not kb_id:
        return {"retrieved_docs": [], "messages": []}

    # 1. Dense retrieval (vector search)
    q_emb = await embed_query(query)
    dense_results = await dense.search(q_emb, kb_id, k=20)

    # 2. Sparse retrieval (BM25)
    # 注意: BM25 搜索返回 (doc_idx, score) 元组
    # 由于 BM25 索引不存储文本，sparse 结果仅用于提升排名
    raw_sparse = sparse.search(query, kb_id, k=20)
    sparse_results = [
        {
            "chunk_id": f"bm25_{idx}",
            "text": "",
            "score": score,
            "doc_id": "",
            "kb_id": kb_id,
        }
        for idx, score in raw_sparse
    ]

    # 3. RRF Fusion - dense + sparse 融合
    fused = hybrid.rrf_fusion(dense_results, sparse_results, top_n=20)

    # 4. Rerank with CrossEncoder
    from app.retrieval.reranker import rerank
    final_docs = await rerank(query, fused, top_n=5)

    return {"retrieved_docs": final_docs, "messages": []}
