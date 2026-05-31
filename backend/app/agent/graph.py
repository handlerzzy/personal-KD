from __future__ import annotations

from collections.abc import AsyncGenerator

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.qa_node import qa_node, qa_node_stream
from app.agent.nodes.retrieval_node import retrieval_node
from app.agent.state import AgentState

_graph = None


def build_graph():
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(AgentState)

    # Nodes
    builder.add_node("retrieve", retrieval_node)
    builder.add_node("qa", qa_node)

    # Edges
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "qa")
    builder.add_edge("qa", END)

    _graph = builder.compile()
    return _graph


async def run_chat(
    query: str,
    kb_id: str,
    conversation_id: str,
    history: list | None = None,
) -> dict:
    """Run the chat graph and return result."""
    graph = build_graph()
    initial_state: AgentState = {
        "messages": history or [],
        "kb_id": kb_id,
        "query": query,
        "retrieved_docs": [],
        "reasoning": "",
        "answer": "",
    }
    result = await graph.ainvoke(initial_state)
    return result


async def stream_chat(
    query: str,
    kb_id: str,
    conversation_id: str,
    history: list | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream chat response token by token.

    Yields dicts with types: reasoning, answer, sources, done
    """
    # Use the streaming QA node directly for token-level streaming
    from app.document.embedder import embed_query
    from app.retrieval import dense, hybrid, sparse

    # 1. Retrieve
    q_emb = await embed_query(query)
    dense_results = await dense.search(q_emb, kb_id, k=20)
    raw_sparse = sparse.search(query, kb_id, k=20)
    sparse_results = [
        {"chunk_id": f"bm25_{idx}", "text": "", "score": score, "doc_id": "", "kb_id": kb_id}
        for idx, (_, score) in enumerate(raw_sparse)
    ]
    fused = hybrid.rrf_fusion(dense_results, sparse_results, top_n=20)

    from app.retrieval.reranker import rerank
    final_docs = await rerank(query, fused, top_n=5)

    # 2. Build state for streaming
    state: AgentState = {
        "messages": history or [],
        "kb_id": kb_id,
        "query": query,
        "retrieved_docs": final_docs,
        "reasoning": "",
        "answer": "",
    }

    # 3. Stream
    async for event in qa_node_stream(state):
        yield event
