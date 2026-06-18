from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import ChatGenerationChunk
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState
from app.answer_cleaner import strip_answer
from app.utils.sources import build_sources

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


from app.llm_cache import get_llm as _get_cached_llm  # noqa: E402

_THINKING_BUDGET_MAP = {
    "factual": 1024,  # 简单事实查询，适度推理
    "summary": 2048,  # 总结类查询，中等推理
    "analytical": 4096,  # 分析类查询，深度推理
    "multi_hop": 4096,  # 多跳查询，重度推理
}

# Module-level cache for _ReasoningChatOpenAI instances
_reasoning_llm_cache: dict[str, _ReasoningChatOpenAI] = {}


def _get_llm(
    streaming: bool = True,
    enable_thinking: bool = True,
    query_type: str = "",
) -> _ReasoningChatOpenAI:
    """Get a cached _ReasoningChatOpenAI instance.

    Caches by (streaming, enable_thinking, budget) to avoid recreating
    _ReasoningChatOpenAI instances on every call. The MiMo LLM API has a
    cold start issue where the first call takes 15-20 seconds, while
    subsequent calls only take 2-4 seconds.

    Thinking budget is dynamically sized based on query_type:
    - factual: 1024 (simple extraction, moderate reasoning)
    - summary: 2048 (synthesis, moderate reasoning)
    - analytical: 4096 (deep analysis, heavy reasoning)
    - multi_hop: 4096 (multi-step reasoning, heavy thinking)

    For non-retrieval queries (simple chat), thinking is disabled to save resources.
    """
    budget = _THINKING_BUDGET_MAP.get(query_type, 2048) if enable_thinking else 0
    cache_key = f"{streaming}:{enable_thinking}:{budget}"

    # Check module-level cache first
    if cache_key in _reasoning_llm_cache:
        return _reasoning_llm_cache[cache_key]

    # Cache miss — create via base cache and wrap
    base_llm = _get_cached_llm(
        streaming=streaming, enable_thinking=enable_thinking, thinking_budget=budget
    )

    llm = _ReasoningChatOpenAI(
        model=base_llm.model_name,
        api_key=base_llm.openai_api_key,
        base_url=base_llm.openai_api_base,
        temperature=base_llm.temperature,
        streaming=base_llm.streaming,
        extra_body=base_llm.extra_body,
    )
    _reasoning_llm_cache[cache_key] = llm
    return llm


def _build_context(docs: list[dict]) -> str:
    if not docs:
        return "未找到相关文档。"
    parts = []
    for i, d in enumerate(docs):
        heading = d.get("metadata", {}).get("heading", "") or ""
        text = d["text"]
        if heading:
            parts.append(f"[{i + 1}] 【{heading}】{text}")
        else:
            parts.append(f"[{i + 1}] {text}")
    return "\n\n".join(parts)


def _build_system_prompt(context: str, has_docs: bool = True) -> str:
    if not has_docs:
        return (
            "你是一个智能助手。用户的问题不需要从知识库检索，请直接回答。\n\n"
            "## 回答规则\n"
            "1. 根据你的知识直接回答问题\n"
            "2. 提供准确、有用的信息\n"
            "3. 用中文回答，简洁完整\n\n"
            "## 禁止内容\n"
            "- JSON 格式数据、文档评分标签、验证分数等内部处理信息\n"
            "- [1][2][3] 等引用编号\n"
        )

    return (
        "你是一个知识库问答助手。基于以下参考文档回答问题。\n\n"
        "## 回答规则\n"
        "1. 基于文档内容回答，保持原意但用自然语言表达\n"
        "2. 如果文档中找不到答案，说明「根据现有文档无法回答」\n"
        "3. 保持准确，数字、名称、术语与文档一致\n"
        '4. 引用来源时使用文档标题或章节名称（如"根据《XXX》..."），不要使用 [1][2][3] 等引用编号\n'
        "5. 用中文回答，简洁完整\n"
        "6. 回答结构：先给出核心答案，再补充细节和来源说明\n\n"
        "## 多文档处理\n"
        "- 当多文档信息一致时，综合回答\n"
        "- 当多文档信息冲突时，标注不同来源并说明差异\n"
        "- 优先使用最新、最权威的来源\n\n"
        "## 禁止内容\n"
        "- JSON 格式数据、文档评分标签、验证分数\n"
        "- 任何内部处理信息、元数据\n"
        "- [1][2][3] 等引用编号\n\n"
        f"## 参考文档\n{context}"
    )


def _strip_internal_data(text: str) -> str:
    """Strip internal pipeline data from LLM output.

    Delegates to shared :func:`strip_answer` in ``app.answer_cleaner``.
    """
    return strip_answer(text)


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------


async def qa_node(state: AgentState) -> dict:
    """Generate answer using LLM with retrieved context.

    Uses ``llm.astream()`` so that LangGraph's
    ``graph.astream(stream_mode="messages")`` receives token-level
    ``AIMessageChunk`` objects via the ``on_llm_new_token`` callback.
    ``ainvoke`` does NOT trigger streaming callbacks — it collects the
    complete response internally, so the frontend never sees individual tokens.
    """
    query = state["query"]
    needs_retrieval = state.get("needs_retrieval", True)
    query_type = state.get("query_type", "")
    # Use retrieved_docs directly (reranker already filters/scores)
    docs = state.get("retrieved_docs", [])

    logger.info(
        "qa_node start: query_type=%s, needs_retrieval=%s, doc_count=%d, query=%.80s",
        query_type,
        needs_retrieval,
        len(docs),
        query,
    )

    # Build the message list for the LLM call
    has_docs = bool(docs)
    context = _build_context(docs)
    system_prompt = _build_system_prompt(context, has_docs=has_docs)

    llm_messages = [SystemMessage(content=system_prompt)]

    # Include conversation history with dynamic window based on query type.
    # Use msg.type ("human"/"ai") not msg.role — LangChain BaseMessage
    # objects do NOT expose a "role" attribute; getattr(msg, "role") always
    # returns "" which silently dropped the entire history.
    _HISTORY_WINDOW = {  # noqa: N806
        "factual": 4,  # 2 rounds
        "summary": 6,  # 3 rounds
        "analytical": 8,  # 4 rounds
        "multi_hop": 10,  # 5 rounds
    }
    history_msgs = state.get("messages", [])
    window = _HISTORY_WINDOW.get(query_type, 8)
    for msg in history_msgs[-window:]:
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "")
            content = getattr(msg, "content", "")
        if role == "human" and content:
            llm_messages.append(HumanMessage(content=content))
        elif role == "ai" and content:
            llm_messages.append(AIMessage(content=content))

    # Append the current query if it's not already the last message
    # (avoids duplication when checkpointer restores full history including
    # the current query, which _build_initial_state may include).
    if not (
        llm_messages
        and isinstance(llm_messages[-1], HumanMessage)
        and llm_messages[-1].content == query
    ):
        llm_messages.append(HumanMessage(content=query))

    # Call LLM with astream — this triggers on_llm_new_token callbacks
    # so that LangGraph's StreamMessagesHandler can emit individual chunks.
    # Disable thinking for non-retrieval queries to save resources.
    # Use dynamic thinking budget based on query_type.
    llm = _get_llm(streaming=True, enable_thinking=needs_retrieval, query_type=query_type)
    full_content = ""
    full_reasoning = ""

    async for chunk in llm.astream(llm_messages):
        # Accumulate content
        if chunk.content:
            full_content += chunk.content
        # Accumulate reasoning from additional_kwargs
        reasoning = chunk.additional_kwargs.get("reasoning_content", "")
        if reasoning:
            full_reasoning += reasoning

    # Strip any internal data that leaked into the answer
    content = _strip_internal_data(full_content)
    reasoning = full_reasoning

    sources = build_sources(docs)

    logger.info(
        "qa_node done: answer_len=%d, reasoning_len=%d, sources_count=%d",
        len(content),
        len(reasoning),
        len(sources),
    )

    # Return messages to state so the checkpointer persists conversation
    # history. Without this, state["messages"] stays empty across turns
    # and the LLM never sees prior conversation context.
    #
    # This does NOT cause duplicate streaming: qa_node calls llm.astream()
    # directly (not chain.ainvoke()), so on_chain_end never fires and the
    # returned AIMessage is only written to state via the add_messages
    # reducer — it is never yielded as a stream chunk.
    return {
        "answer": content,
        "reasoning": reasoning,
        "sources": sources,
        "messages": [
            HumanMessage(content=query),
            AIMessage(content=content),
        ],
    }
