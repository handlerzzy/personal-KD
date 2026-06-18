"""Agentic RAG Graph — orchestrates the full retrieval-augmented generation pipeline.

Architecture:
    START → classify_query → [needs_retrieval?]
        [true]  → retrieve → generate_answer → [verify?] → END
        [false] → generate_answer → END

Optimizations:
    - grade_documents removed: reranker already filters/scores documents
    - Non-retrieval queries skip verify_answer to save LLM calls
    - verify_answer only runs for multi_hop queries
    - Thinking budget is dynamically adjusted based on query complexity
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.answer_verifier import refine_answer, verify_answer
from app.agent.nodes.qa_node import qa_node
from app.agent.nodes.query_classifier import classify_query
from app.agent.nodes.retrieval_node import retrieval_node
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

_graph = None
_checkpointer: AsyncSqliteSaver | None = None
_conn: aiosqlite.Connection | None = None


async def init_checkpointer(db_path: str = "data/agent.db") -> AsyncSqliteSaver:
    """Initialize the SQLite checkpointer for LangGraph."""
    global _checkpointer, _conn
    if _checkpointer is None:
        _conn = await aiosqlite.connect(db_path)
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA busy_timeout=5000")
        _checkpointer = AsyncSqliteSaver(_conn)
        logger.info("Checkpointer initialized: %s", db_path)
    return _checkpointer


async def close_checkpointer() -> None:
    """Close the checkpointer connection."""
    global _checkpointer, _graph, _conn
    if _conn is not None:
        await _conn.close()
        _conn = None
    _checkpointer = None
    _graph = None
    logger.info("Checkpointer closed")


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------


def _decide_retrieval(state: AgentState) -> str:
    """Decide whether to retrieve documents or skip directly to answer generation.

    - If needs_retrieval is True → retrieve documents
    - If needs_retrieval is False → skip retrieval, generate answer directly
    """
    needs_retrieval = state.get("needs_retrieval", True)
    if needs_retrieval:
        return "retrieve"
    logger.info("Query does not need retrieval, skipping to generate_answer")
    return "generate_answer"


def _decide_refine(state: AgentState) -> str:
    """Decide whether to refine the answer or finish.

    - If needs_refine is True → refine
    - Otherwise → end
    """
    needs_refine = state.get("needs_refine", False)
    if needs_refine:
        logger.info("Answer needs refinement, triggering refine_answer")
        return "refine"
    return "__end__"


def _decide_after_generate(state: AgentState) -> str:
    """Decide next step after answer generation.

    Decision logic (in order):
    1. Non-retrieval query (needs_retrieval=False) → END (no docs to verify against)
    2. factual/summary/analytical query → END (low/medium risk, fast response)
    3. multi_hop query → verify_answer (full verification, high risk)
    """
    needs_retrieval = state.get("needs_retrieval", True)
    if not needs_retrieval:
        logger.info("Non-retrieval query, skipping answer verification")
        return "__end__"

    query_type = state.get("query_type", "")
    # 仅 multi_hop 需要验证（analytical 风险较低，跳过验证提升效率）
    if query_type == "multi_hop":
        return "verify_answer"

    logger.info("Query type '%s', skipping verification", query_type)
    return "__end__"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph():
    """Build the Agentic RAG graph with conditional routing.

    Simplified pipeline: classify → retrieve → generate → [verify → refine]
    - grade_documents removed: reranker already filters/scores documents
    - rewrite_query removed: not needed without grade step
    """
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(AgentState)

    # ---- Nodes ----
    builder.add_node("classify_query", classify_query)
    builder.add_node("retrieve", retrieval_node)
    builder.add_node("generate_answer", qa_node)
    builder.add_node("verify_answer", verify_answer)
    builder.add_node("refine_answer", refine_answer)

    # ---- Edges ----
    # START → classify → conditional retrieve or skip to generate
    builder.add_edge(START, "classify_query")
    builder.add_conditional_edges(
        "classify_query",
        _decide_retrieval,
        {
            "retrieve": "retrieve",
            "generate_answer": "generate_answer",
        },
    )

    # Retrieve → generate directly (no grading, reranker handles filtering)
    builder.add_edge("retrieve", "generate_answer")

    # Generate → conditional: verify or skip to END
    builder.add_conditional_edges(
        "generate_answer",
        _decide_after_generate,
        {
            "verify_answer": "verify_answer",
            "__end__": END,
        },
    )
    builder.add_conditional_edges(
        "verify_answer",
        _decide_refine,
        {
            "refine": "refine_answer",
            "__end__": END,
        },
    )
    builder.add_edge("refine_answer", END)

    _graph = builder.compile(checkpointer=_checkpointer)
    logger.info("Agentic RAG graph compiled successfully")
    return _graph


# ---------------------------------------------------------------------------
# Initial state builder
# ---------------------------------------------------------------------------


def _build_initial_state(
    query: str,
    kb_id: str,
) -> AgentState:
    """Build initial state with defaults for all Agentic RAG fields.

    IMPORTANT: We do NOT pass ``messages`` in the initial state. The
    checkpointer (via ``add_messages`` reducer) owns conversation history
    and restores it from the previous checkpoint when ``thread_id`` matches.

    If we included messages here, ``_messages_from_dicts`` would create
    objects with *new* IDs that don't match the checkpoint's IDs, causing
    ``add_messages`` to append them as duplicates instead of merging.
    ``qa_node`` reads history from ``state["messages"]`` (restored by the
    checkpointer) and appends the current query explicitly.
    """
    return {
        "messages": [],
        "kb_id": kb_id,
        "query": query,
        "retrieved_docs": [],
        "reasoning": "",
        "answer": "",
        # Agentic RAG defaults
        "query_type": "",
        "needs_retrieval": True,
        "search_strategy": {},
        "original_query": query,
        "quality_score": 0.0,
        "verify_feedback": "",
        "needs_refine": False,
    }


# ---------------------------------------------------------------------------
# Chat runners
# ---------------------------------------------------------------------------


async def run_chat(
    query: str,
    kb_id: str,
    conversation_id: str,
    history: list | None = None,
) -> dict:
    """Run the chat graph and return result (non-streaming, used by evaluator).

    120-second timeout prevents hanging on LLM cold start or API issues.
    """
    graph = build_graph()
    config = {"configurable": {"thread_id": conversation_id}}

    initial_state = _build_initial_state(query, kb_id)
    try:
        result = await asyncio.wait_for(
            graph.ainvoke(initial_state, config=config),
            timeout=120.0,
        )
        return result
    except TimeoutError:
        logger.error(
            "Graph execution timed out (120s): kb_id=%s, conv_id=%s",
            kb_id,
            conversation_id,
        )
        return {"answer": "对话处理超时，请重试", "retrieved_docs": []}


async def stream_chat(
    query: str,
    kb_id: str,
    conversation_id: str,
    history: list | None = None,
) -> AsyncGenerator[tuple, None]:
    """Stream chat via compiled graph using ["updates", "messages"] modes.

    Has a 120-second timeout to prevent hanging on LLM cold start or API issues.

    Yields (mode, data) tuples:
    - mode="updates" → data = {node_name: node_output}
    - mode="messages" → data = (AIMessageChunk, metadata)
    """
    graph = build_graph()
    config = {"configurable": {"thread_id": conversation_id}}

    initial_state = _build_initial_state(query, kb_id)

    try:
        async with asyncio.timeout(120.0):
            async for mode, data in graph.astream(
                initial_state,
                config=config,
                stream_mode=["updates", "messages"],
            ):
                yield (mode, data)
    except TimeoutError:
        logger.error(
            "Graph execution timed out (120s): kb_id=%s, conv_id=%s",
            kb_id,
            conversation_id,
        )
        yield ("error", {"message": "对话处理超时，请重试"})
