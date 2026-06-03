from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import ChatGenerationChunk
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ChatOpenAI subclass that preserves reasoning_content
# ---------------------------------------------------------------------------


class _ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI subclass that preserves ``reasoning_content`` from streaming deltas.

    The upstream ``_convert_delta_to_message_chunk`` discards ``reasoning_content``
    and other non-standard fields. This override injects it into
    ``additional_kwargs`` so downstream code (e.g. ``chat.py`` event_generator)
    can read ``chunk.additional_kwargs["reasoning_content"]``.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is None:
            return None

        # Extract reasoning_content from the raw delta and attach to additional_kwargs
        choices = chunk.get("choices", [])
        if choices:
            delta = choices[0].get("delta") or {}
            reasoning = delta.get("reasoning_content")
            if reasoning and gen_chunk.message is not None:
                gen_chunk.message.additional_kwargs["reasoning_content"] = reasoning

        return gen_chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_llm(streaming: bool = True) -> _ReasoningChatOpenAI:
    """Create a ChatOpenAI instance targeting the LLM API endpoint.

    Streaming is enabled by default so that ``graph.astream(stream_mode="messages")``
    receives token-level ``AIMessageChunk`` objects from LangGraph.
    """
    return _ReasoningChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_api_base,
        temperature=0.7,
        streaming=streaming,
    )


def _build_context(docs: list[dict]) -> str:
    if not docs:
        return "未找到相关文档。"
    return "\n\n".join(f"[{i+1}] {d['text']}" for i, d in enumerate(docs))


def _build_system_prompt(context: str) -> str:
    return (
        "你是一个知识库问答助手。基于以下检索到的文档内容回答问题。\n"
        "如果你不知道答案，请直接说不知道，不要编造。\n"
        "引用来源时标注编号。请用中文回答。\n\n"
        f"参考文档：\n{context}"
    )


def _build_sources(docs: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": d.get("chunk_id", ""),
            "text": d.get("text", "")[:200],
            "score": round(d.get("score", 0.0), 4),
            "doc_id": d.get("doc_id", ""),
        }
        for d in docs
    ]


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------


async def qa_node(state: AgentState) -> dict:
    """Generate answer using LLM with retrieved context.

    Uses ``ChatOpenAI(streaming=True)`` so that LangGraph's
    ``astream(stream_mode="messages")`` can yield token-level chunks to the
    frontend.  When called via ``ainvoke`` (non-streaming), LangGraph collects
    all chunks internally and returns the full ``AIMessage``.
    """
    query = state["query"]
    docs = state.get("retrieved_docs", [])

    # Build the message list for the LLM call
    context = _build_context(docs)
    system_prompt = _build_system_prompt(context)

    llm_messages = [SystemMessage(content=system_prompt)]

    # Include last 10 turns from conversation history (if present)
    history_msgs = state.get("messages", [])
    for msg in history_msgs[-10:]:
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role == "user" and content:
            llm_messages.append(HumanMessage(content=content))
        elif role == "assistant" and content:
            llm_messages.append(AIMessage(content=content))

    llm_messages.append(HumanMessage(content=query))

    # Call LLM
    llm = _get_llm(streaming=True)
    response = await llm.ainvoke(llm_messages)

    content = response.content or ""
    reasoning = response.additional_kwargs.get("reasoning_content", "")

    sources = _build_sources(docs)

    return {
        "answer": content,
        "reasoning": reasoning,
        "sources": sources,
        "messages": [AIMessage(content=content)],
    }
