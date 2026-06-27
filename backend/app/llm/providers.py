"""LLM Provider abstraction — model-specific configuration for API calls.

Supports OpenAI-compatible providers by centralizing their configuration
differences in a single lookup table. Adding a new provider is a one-line
change — add an entry to ``_PROVIDER_CONFIG``.

Provider comparison
===================
+------------------+--------+----------+--------+----------+
| Provider         | thinks | effort   | reason | effort   |
|                  | extra  | levels   | stream | mapping  |
+------------------+--------+----------+--------+----------+
| MiMo             |  ✓     | "high"   |  ✓    | on/off   |
|                  |        |          |       | only     |
+------------------+--------+----------+--------+----------+
| DeepSeek         |  ✓     | high,    |  ✓    | high →   |
|                  |        | max      |       | high     |
|                  |        |          |       | max → max|
+------------------+--------+----------+--------+----------+
| OpenAI generic   |        |          |       |          |
+------------------+--------+----------+--------+----------+
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ModelProvider(StrEnum):
    """Supported LLM providers — all OpenAI-compatible.

    Usage::

        provider = get_provider(settings.llm_provider)
        kwargs = get_llm_kwargs(provider, enable_thinking=True, effort="high")
        llm = ChatOpenAI(model=..., **kwargs)
    """

    MIMO = "mimo"
    DEEPSEEK = "deepseek"
    OPENAI_COMPATIBLE = "openai"  # generic catch-all


# --------------------------------------------------------------------------
# Per-provider configuration table
#
# To add a new provider: 1) add an enum member above, 2) add a row here.
# Each row declares:
#   needs_thinking_extra_body — whether to pass thinking.type in extra_body
#   supports_reasoning_stream — whether delta.reasoning_content is populated
#   effort_levels — list of thinking intensities this provider can distinguish
#                   (empty list = no thinking support; ["high"] = on/off only)
# --------------------------------------------------------------------------

_ProviderConfig = dict[str, Any]

_PROVIDER_CONFIG: dict[ModelProvider, _ProviderConfig] = {
    ModelProvider.MIMO: {
        "needs_thinking_extra_body": True,
        "supports_reasoning_stream": True,
        "effort_levels": ["high"],  # on/off only, no gradation
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    ModelProvider.DEEPSEEK: {
        "needs_thinking_extra_body": True,
        "supports_reasoning_stream": True,
        "effort_levels": ["high", "max"],
        # Mild frequency penalty discourages the repetition loops that some
        # DeepSeek variants (v4-flash) occasionally enter mid-generation,
        # where the model re-generates the user's query and re-answers it.
        "frequency_penalty": 0.3,
        "presence_penalty": 0.0,
    },
    ModelProvider.OPENAI_COMPATIBLE: {
        "needs_thinking_extra_body": False,
        "supports_reasoning_stream": False,
        "effort_levels": [],
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def get_provider(provider_name: str) -> ModelProvider:
    """Resolve a provider name string to a ``ModelProvider`` enum.

    Falls back to ``OPENAI_COMPATIBLE`` on unknown names for forward
    compatibility (e.g. someone sets ``LLM_PROVIDER=ollama``).
    """
    try:
        return ModelProvider(provider_name.lower())
    except ValueError:
        logger.warning(
            "Unknown provider '%s', falling back to 'openai'. "
            "Supported values: mimo, deepseek, openai",
            provider_name,
        )
        return ModelProvider.OPENAI_COMPATIBLE


def get_llm_kwargs(
    provider: ModelProvider,
    enable_thinking: bool = True,
    effort: str = "high",
) -> dict[str, Any]:
    """Build provider-specific kwargs for constructing a ``ChatOpenAI`` instance.

    Business-layer concepts (enable/disable thinking, thinking intensity)
    are translated here into the wire format each provider understands.

    Returns a dict that can be unpacked: ``ChatOpenAI(model=..., **kwargs)``.

    Kwargs returned (subset depending on provider):
    - ``extra_body`` — ``thinking.type`` enable/disable
    - ``model_kwargs`` — ``reasoning_effort`` when effort is "max"
    - ``frequency_penalty`` — mild penalty for DeepSeek to avoid repetition
    - ``presence_penalty`` — set per provider config (default 0.0)
    """
    config = _PROVIDER_CONFIG.get(provider, _PROVIDER_CONFIG[ModelProvider.OPENAI_COMPATIBLE])
    kwargs: dict[str, Any] = {}

    # -- extra_body: thinking enable / disable --
    if config["needs_thinking_extra_body"]:
        if enable_thinking:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            # Explicitly disable thinking for all providers that support it.
            # Without this, some providers (DeepSeek) may default to thinking
            # enabled and return only reasoning_tokens without content, which
            # breaks short-generation tasks like title extraction.
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    # -- reasoning_effort: only DeepSeek supports "max" --
    if enable_thinking and effort == "max" and "max" in config.get("effort_levels", []):
        kwargs.setdefault("model_kwargs", {})["reasoning_effort"] = "max"

    # -- frequency_penalty / presence_penalty: discourage repetition --
    # DeepSeek uses mild penalty (0.3) to prevent repetition loops.
    freq = config.get("frequency_penalty", 0.0)
    pres = config.get("presence_penalty", 0.0)
    if freq:
        kwargs["frequency_penalty"] = freq
    if pres:
        kwargs["presence_penalty"] = pres

    return kwargs


def supports_reasoning_stream(provider: ModelProvider) -> bool:
    """Whether this provider streams ``reasoning_content`` tokens during generation.

    ``True`` for MiMo and DeepSeek (both emit ``reasoning_content`` in
    streaming deltas). ``False`` for generic OpenAI-compatible models.
    """
    config = _PROVIDER_CONFIG.get(provider, _PROVIDER_CONFIG[ModelProvider.OPENAI_COMPATIBLE])
    return config["supports_reasoning_stream"]
