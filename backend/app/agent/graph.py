from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import aiosqlite
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.qa_node import qa_node
from app.agent.nodes.retrieval_node import retrieval_node
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

_graph = None
_checkpointer: AsyncSqliteSaver | None = None
_conn: aiosqlite.Connection | None = None


async def init_checkpointer(db_path: str = "data/agent.db") -> AsyncSqliteSaver:
    """Initialize the SQLite checkpointer for LangGraph.

    Uses manual aiosqlite connection management (rather than the
    ``from_conn_string`` context manager) to avoid compatibility issues
    with ``__aenter__`` / ``__aexit__`` lifecycle.
    """
    global _checkpointer, _conn
    if _checkpointer is None:
        _conn = await aiosqlite.connect(db_path)
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
    _graph = None  # force rebuild with next init_checkpointer
    logger.info("Checkpointer closed")


def build_graph():
    """Build the LangGraph graph with checkpointer."""
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

    _graph = builder.compile(checkpointer=_checkpointer)
    return _graph


# ---------------------------------------------------------------------------
# Message conversion helpers
# ---------------------------------------------------------------------------


def _messages_from_dicts(history: list[dict] | None) -> list[BaseMessage]:
    """Convert DB dict-style messages to LangChain ``BaseMessage`` objects.

    System messages and other roles that don't map to Human/AI are skipped
    because the system prompt is injected inside ``qa_node`` each invocation.
    """
    if not history:
        return []
    result: list[BaseMessage] = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not content:
            continue
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
    return result


# ---------------------------------------------------------------------------
# Chat runners
# ---------------------------------------------------------------------------


async def run_chat(
    query: str,
    kb_id: str,
    conversation_id: str,
    history: list | None = None,
) -> dict:
    """Run the chat graph and return result (non-streaming, used by evaluator)."""
    graph = build_graph()
    config = {"configurable": {"thread_id": conversation_id}}

    converted_messages = _messages_from_dicts(history)

    initial_state: AgentState = {
        "messages": converted_messages,
        "kb_id": kb_id,
        "query": query,
        "retrieved_docs": [],
        "reasoning": "",
        "answer": "",
    }
    result = await graph.ainvoke(initial_state, config=config)
    return result


async def stream_chat(
    query: str,
    kb_id: str,
    conversation_id: str,
    history: list | None = None,
) -> AsyncGenerator[tuple, None]:
    """Stream chat via compiled graph using ``["updates", "messages"]`` modes.

    Yields ``(mode, data)`` tuples:

    - ``mode="updates"`` → ``data = {node_name: node_output}`` (e.g. sources from retrieve)
    - ``mode="messages"`` → ``data = (AIMessageChunk, metadata)`` (token-level LLM output)
    """
    graph = build_graph()
    config = {"configurable": {"thread_id": conversation_id}}

    converted_messages = _messages_from_dicts(history)

    initial_state: AgentState = {
        "messages": converted_messages,
        "kb_id": kb_id,
        "query": query,
        "retrieved_docs": [],
        "reasoning": "",
        "answer": "",
    }

    async for mode, data in graph.astream(
        initial_state,
        config=config,
        stream_mode=["updates", "messages"],
    ):
        yield (mode, data)
