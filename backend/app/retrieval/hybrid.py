from __future__ import annotations


def rrf_fusion(
    dense_results: list[dict],
    sparse_results: list[dict],
    k: int = 60,
    top_n: int = 20,
) -> list[dict]:
    """Fuse dense and sparse results using RRF (Reciprocal Rank Fusion).

    Formula: score(doc) = Σ 1/(k + rank(doc))

    Note: k=60 balances precision and recall for knowledge base Q&A.
    """
    rrf_scores: dict[str, dict] = {}

    # Process dense results
    for rank, doc in enumerate(dense_results):
        cid = doc["chunk_id"]
        if cid not in rrf_scores:
            rrf_scores[cid] = {**doc, "rrf_score": 0.0, "dense_rank": rank + 1, "sparse_rank": None}
        rrf_scores[cid]["rrf_score"] += 1.0 / (k + rank + 1)
        rrf_scores[cid]["dense_rank"] = rank + 1

    # Process sparse results
    for rank, doc in enumerate(sparse_results):
        cid = doc["chunk_id"]
        if cid not in rrf_scores:
            rrf_scores[cid] = {**doc, "rrf_score": 0.0, "dense_rank": None, "sparse_rank": rank + 1}
        rrf_scores[cid]["rrf_score"] += 1.0 / (k + rank + 1)
        rrf_scores[cid]["sparse_rank"] = rank + 1

    # Sort by RRF score descending
    sorted_docs = sorted(
        rrf_scores.values(),
        key=lambda x: x["rrf_score"],
        reverse=True,
    )

    # Remove internal fields and limit
    result = []
    for doc in sorted_docs[:top_n]:
        result.append(
            {
                "chunk_id": doc["chunk_id"],
                "text": doc["text"],
                "score": doc["rrf_score"],
                "doc_id": doc.get("doc_id", ""),
                "kb_id": doc.get("kb_id", ""),
            }
        )
    return result
