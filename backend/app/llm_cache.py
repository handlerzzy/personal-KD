"""LLM client cache — reuse ChatOpenAI instances to avoid cold start latency.

The MiMo LLM API has a cold start issue where the first call takes 15-20 seconds,
while subsequent calls only take 2-4 seconds. By caching and reusing the ChatOpenAI
client, we avoid creating new HTTP connections for each request.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# Cache: key = (streaming, enable_thinking, thinking_budget) -> ChatOpenAI instance
_llm_cache: dict[tuple[bool, bool, int], ChatOpenAI] = {}


def get_llm(
    streaming: bool = True,
    enable_thinking: bool = True,
    temperature: float = 0.7,
    thinking_budget: int = 2048,
    **kwargs: Any,
) -> ChatOpenAI:
    """Get a cached ChatOpenAI instance.

    Args:
        streaming: Whether to enable streaming mode.
        enable_thinking: Whether to enable MiMo thinking mode.
        temperature: LLM temperature.
        thinking_budget: Max tokens for thinking (only used when enable_thinking=True).
            Dynamically sized per query type: factual=1024, analytical=4096, multi_hop=4096.
        **kwargs: Additional ChatOpenAI parameters.

    Returns:
        Cached ChatOpenAI instance.
    """
    cache_key = (streaming, enable_thinking, thinking_budget)

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    thinking_config = (
        {"thinking": {"type": "enabled", "budget_tokens": thinking_budget}}
        if enable_thinking
        else {"thinking": {"type": "disabled"}}
    )

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_api_base,
        temperature=temperature,
        streaming=streaming,
        extra_body=thinking_config,
        **kwargs,
    )

    _llm_cache[cache_key] = llm
    logger.info(
        "Cached ChatOpenAI instance: streaming=%s, enable_thinking=%s, budget=%s",
        streaming,
        enable_thinking,
        thinking_budget,
    )
    return llm


def get_simple_llm(temperature: float = 0, streaming: bool = False) -> ChatOpenAI:
    """Get a simple ChatOpenAI instance (no thinking mode) for auxiliary tasks.

    Used by query_classifier, answer_verifier, etc.
    """
    cache_key = (streaming, False, 0)

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_api_base,
        temperature=temperature,
        streaming=streaming,
    )

    _llm_cache[cache_key] = llm
    logger.info("Cached simple ChatOpenAI instance: temperature=%s", temperature)
    return llm


def get_dashscope_llm(temperature: float = 0) -> ChatOpenAI:
    """Get a DashScope qwen-flash instance for fast classification tasks.

    DashScope (阿里云) provides low-latency inference ideal for lightweight
    tasks like query classification. Uses DASHSCOPE_* env vars.
    """
    cache_key = ("dashscope", temperature)

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    llm = ChatOpenAI(
        model=settings.dashscope_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        temperature=temperature,
        streaming=False,
    )

    _llm_cache[cache_key] = llm
    logger.info(
        "Cached DashScope instance: model=%s, base_url=%s",
        settings.dashscope_model,
        settings.dashscope_base_url,
    )
    return llm


async def warmup_llm():
    """Warm up LLM client to avoid cold start latency on first request."""
    import time

    start = time.time()
    llm = get_simple_llm(temperature=0, streaming=False)
    try:
        await llm.ainvoke("hi")
        elapsed = time.time() - start
        logger.info("LLM warmup completed in %.2fs", elapsed)
    except Exception:
        logger.exception("LLM warmup failed (non-fatal)")
