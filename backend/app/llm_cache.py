"""LLM client cache — reuse ChatOpenAI instances to avoid cold start latency.

The first LLM call can take 15-20 seconds (cold start), while subsequent
calls only take 2-4 seconds. By caching and reusing the ChatOpenAI client,
we avoid creating new HTTP connections for each request.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import settings
from app.llm.providers import get_llm_kwargs, get_provider

logger = logging.getLogger(__name__)

# Cache: key = (streaming, enable_thinking, effort) -> ChatOpenAI instance
_llm_cache: dict[tuple[bool, bool, str], ChatOpenAI] = {}


def _get_provider():
    """Resolve the configured provider lazily (supports test mocking)."""
    return get_provider(settings.llm_provider)


def get_llm(
    streaming: bool = True,
    enable_thinking: bool = True,
    temperature: float = 0.7,
    effort: str = "high",
    **kwargs: Any,
) -> ChatOpenAI:
    """Get a cached ChatOpenAI instance.

    Provider-specific parameters (``extra_body``, ``model_kwargs``) are
    resolved via :func:`~app.llm.providers.get_llm_kwargs`.  This ensures
    that only parameters appropriate for the configured provider are sent.

    Args:
        streaming: Whether to enable streaming mode.
        enable_thinking: Whether to enable thinking/reasoning mode.
        temperature: LLM temperature.
        effort: Thinking effort level — an abstract intensity that the
            provider layer maps to the concrete parameter (e.g.
            ``reasoning_effort: "max"`` for DeepSeek, or just
            ``thinking.type: "enabled"`` for MiMo).  ``"high"`` is the
            default; ``"max"`` requests maximum reasoning; empty string
            means thinking is effectively disabled.
        **kwargs: Additional ChatOpenAI parameters.

    Returns:
        Cached ChatOpenAI instance.
    """
    cache_key = (streaming, enable_thinking, effort)

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    # Build provider-specific kwargs (extra_body, model_kwargs, etc.)
    provider = _get_provider()
    provider_kwargs = get_llm_kwargs(
        provider,
        enable_thinking=enable_thinking,
        effort=effort,
    )

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_api_base,
        temperature=temperature,
        streaming=streaming,
        **provider_kwargs,
        **kwargs,
    )

    _llm_cache[cache_key] = llm
    logger.info(
        "Cached ChatOpenAI instance: provider=%s, streaming=%s, enable_thinking=%s, effort=%s",
        settings.llm_provider,
        streaming,
        enable_thinking,
        effort,
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
