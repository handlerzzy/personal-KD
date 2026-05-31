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
    raw_sparse = sparse.search(query, kb_id, k=20)
    sparse_results = []
    # Map BM25 results (id, score) to chunk data
    # bm25x returns (internal_doc_id, score) tuples
    # We need to reconstruct chunk info — BM25 stores by text order
    # For simplicity, we create chunk_id from index
    for idx, (doc_idx, score) in enumerate(raw_sparse):
        sparse_results.append({
            "chunk_id": f"bm25_{doc_idx}",
            "text": "",
            "score": score,
            "doc_id": "",
            "kb_id": kb_id,
        })

    # 3. RRF Fusion
    fused = hybrid.rrf_fusion(dense_results, sparse_results, top_n=20)

    # 4. Rerank with CrossEncoder
    from app.retrieval.reranker import rerank
    final_docs = await rerank(query, fused, top_n=5)

    return {"retrieved_docs": final_docs, "messages": []}
