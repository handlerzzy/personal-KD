"""Tests for llm_cache — ChatOpenAI instance caching and reuse."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.llm_cache import _llm_cache, get_dashscope_llm, get_llm, get_simple_llm


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the LLM cache before and after each test."""
    _llm_cache.clear()
    yield
    _llm_cache.clear()


class TestGetLlm:
    """Test get_llm() caching behavior."""

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_cache_and_return_same_instance(self, mock_settings, mock_cls):
        """Same cache key should return the same cached instance."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        instance = MagicMock()
        mock_cls.return_value = instance

        result1 = get_llm(streaming=True, enable_thinking=True, effort="high")
        result2 = get_llm(streaming=True, enable_thinking=True, effort="high")

        assert result1 is result2
        mock_cls.assert_called_once()  # Only one ChatOpenAI created

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_create_different_instances_for_different_effort(self, mock_settings, mock_cls):
        """Different effort levels should create different instances."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        instance_a = MagicMock(name="instance_a")
        instance_b = MagicMock(name="instance_b")
        mock_cls.side_effect = [instance_a, instance_b]

        result1 = get_llm(streaming=True, enable_thinking=True, effort="high")
        result2 = get_llm(streaming=True, enable_thinking=True, effort="max")

        assert result1 is not result2
        assert mock_cls.call_count == 2

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_use_correct_cache_key_tuple(self, mock_settings, mock_cls):
        """Cache key should be (streaming, enable_thinking, effort)."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        get_llm(streaming=True, enable_thinking=True, effort="max")

        assert (True, True, "max") in _llm_cache

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_pass_thinking_config_when_enabled(self, mock_settings, mock_cls):
        """When enable_thinking=True, extra_body should include thinking config."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        get_llm(streaming=True, enable_thinking=True, effort="high")

        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
        assert "budget_tokens" not in call_kwargs["extra_body"]["thinking"]

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_send_thinking_disabled_when_thinking_disabled(self, mock_settings, mock_cls):
        """When enable_thinking=False for thinking-capable providers, send thinking: disabled."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        get_llm(streaming=False, enable_thinking=False, effort="")

        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["extra_body"]["thinking"]["type"] == "disabled"


class TestGetSimpleLlm:
    """Test get_simple_llm() caching behavior."""

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_cache_simple_instance(self, mock_settings, mock_cls):
        """Same parameters should return the same cached instance."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        instance = MagicMock()
        mock_cls.return_value = instance

        result1 = get_simple_llm(temperature=0, streaming=False)
        result2 = get_simple_llm(temperature=0, streaming=False)

        assert result1 is result2
        mock_cls.assert_called_once()

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_use_fixed_cache_key(self, mock_settings, mock_cls):
        """get_simple_llm always uses cache key (streaming, False, 0)."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        get_simple_llm(temperature=0, streaming=False)

        assert (False, False, 0) in _llm_cache


class TestGetDashscopeLlm:
    """Test get_dashscope_llm() caching behavior."""

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_cache_dashscope_instance(self, mock_settings, mock_cls):
        """Same temperature should return the same cached instance."""
        mock_settings.dashscope_model = "qwen-flash"
        mock_settings.dashscope_api_key = "test-key"
        mock_settings.dashscope_base_url = "https://dashscope.test.com/v1"
        instance = MagicMock()
        mock_cls.return_value = instance

        result1 = get_dashscope_llm(temperature=0)
        result2 = get_dashscope_llm(temperature=0)

        assert result1 is result2
        mock_cls.assert_called_once()

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_use_string_cache_key_for_dashscope(self, mock_settings, mock_cls):
        """DashScope uses ("dashscope", temperature) as cache key."""
        mock_settings.dashscope_model = "qwen-flash"
        mock_settings.dashscope_api_key = "test-key"
        mock_settings.dashscope_base_url = "https://dashscope.test.com/v1"
        mock_cls.return_value = MagicMock()

        get_dashscope_llm(temperature=0.5)

        assert ("dashscope", 0.5) in _llm_cache

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_create_different_instances_for_different_temperatures(
        self, mock_settings, mock_cls
    ):
        """Different temperatures should produce different cached instances."""
        mock_settings.dashscope_model = "qwen-flash"
        mock_settings.dashscope_api_key = "test-key"
        mock_settings.dashscope_base_url = "https://dashscope.test.com/v1"
        instance_a = MagicMock(name="temp0")
        instance_b = MagicMock(name="temp1")
        mock_cls.side_effect = [instance_a, instance_b]

        result1 = get_dashscope_llm(temperature=0)
        result2 = get_dashscope_llm(temperature=1)

        assert result1 is not result2
        assert mock_cls.call_count == 2

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_disable_streaming_for_dashscope(self, mock_settings, mock_cls):
        """DashScope instances should always have streaming=False."""
        mock_settings.dashscope_model = "qwen-flash"
        mock_settings.dashscope_api_key = "test-key"
        mock_settings.dashscope_base_url = "https://dashscope.test.com/v1"
        mock_cls.return_value = MagicMock()

        get_dashscope_llm(temperature=0)

        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["streaming"] is False


class TestCacheClear:
    """Test cache invalidation."""

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_recreate_after_cache_clear(self, mock_settings, mock_cls):
        """After clearing cache, a new instance should be created."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        instance1 = MagicMock(name="first")
        instance2 = MagicMock(name="second")
        mock_cls.side_effect = [instance1, instance2]

        result1 = get_llm(streaming=True, enable_thinking=True, effort="high")
        _llm_cache.clear()
        result2 = get_llm(streaming=True, enable_thinking=True, effort="high")

        assert result1 is not result2
        assert mock_cls.call_count == 2


class TestDeterministicKeys:
    """Test that cache keys are deterministic."""

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_should_produce_same_key_for_same_args(self, mock_settings, mock_cls):
        """Calling get_llm twice with identical args should hit cache."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        results = [
            get_llm(streaming=True, enable_thinking=True, effort="high") for _ in range(5)
        ]

        assert all(r is results[0] for r in results)
        mock_cls.assert_called_once()


class TestProviderIntegration:
    """Integration tests: get_llm() with different providers."""

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_deepseek_should_not_send_budget_tokens(self, mock_settings, mock_cls):
        """DeepSeek: get_llm should NOT include budget_tokens in extra_body."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        get_llm(streaming=True, enable_thinking=True, effort="high")

        call_kwargs = mock_cls.call_args[1]
        extra = call_kwargs.get("extra_body", {})
        assert extra == {"thinking": {"type": "enabled"}}
        assert "budget_tokens" not in extra.get("thinking", {})

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_deepseek_should_include_reasoning_effort_max(self, mock_settings, mock_cls):
        """DeepSeek: get_llm with effort='max' should include reasoning_effort."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        get_llm(streaming=True, enable_thinking=True, effort="max")

        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs.get("model_kwargs", {}).get("reasoning_effort") == "max"

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_deepseek_should_not_include_reasoning_effort_default(self, mock_settings, mock_cls):
        """DeepSeek: get_llm with effort='high' should NOT include reasoning_effort."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        get_llm(streaming=True, enable_thinking=True, effort="high")

        call_kwargs = mock_cls.call_args[1]
        assert "model_kwargs" not in call_kwargs

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_deepseek_should_send_thinking_disabled(self, mock_settings, mock_cls):
        """DeepSeek: extra_body with thinking:disabled when thinking is off."""
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.deepseek.com/v1"
        mock_settings.llm_provider = "deepseek"
        mock_cls.return_value = MagicMock()

        get_llm(streaming=False, enable_thinking=False, effort="")

        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["extra_body"]["thinking"]["type"] == "disabled"
        assert "model_kwargs" not in call_kwargs

    @patch("app.llm_cache.ChatOpenAI")
    @patch("app.llm_cache.settings")
    def test_openai_should_send_no_extra_body(self, mock_settings, mock_cls):
        """OpenAI: no extra_body regardless of thinking setting."""
        mock_settings.llm_model = "gpt-4o"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_api_base = "https://api.openai.com/v1"
        mock_settings.llm_provider = "openai"
        mock_cls.return_value = MagicMock()

        get_llm(streaming=True, enable_thinking=True, effort="high")

        call_kwargs = mock_cls.call_args[1]
        assert "extra_body" not in call_kwargs
