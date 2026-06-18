"""Tests for query_classifier — classifies user queries and determines retrieval strategy."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agent.nodes.query_classifier import _parse_classification, classify_query
from langchain_core.messages import AIMessage

# Common LLM response payloads for tests
_RESP_FACTUAL = (
    '{"needs_retrieval": true, "query_type": "factual",'
    ' "use_hyde": false, "multi_query_count": 1}'
)
_RESP_ANALYTICAL = (
    '{"needs_retrieval": true, "query_type": "analytical",'
    ' "use_hyde": true, "multi_query_count": 3}'
)
_RESP_MULTI_HOP = (
    '{"needs_retrieval": true, "query_type": "multi_hop",'
    ' "use_hyde": true, "multi_query_count": 3}'
)

# ---------------------------------------------------------------------------
# _parse_classification (pure function, no mocking needed)
# ---------------------------------------------------------------------------


class TestParseClassification:
    """Test the JSON parsing helper."""

    def test_should_parse_valid_json(self):
        raw = _RESP_FACTUAL
        result = _parse_classification(raw)
        assert result["needs_retrieval"] is True
        assert result["query_type"] == "factual"
        assert result["use_hyde"] is False
        assert result["multi_query_count"] == 1

    def test_should_parse_json_wrapped_in_markdown_code_block(self):
        raw = f"```json\n{_RESP_ANALYTICAL}\n```"
        result = _parse_classification(raw)
        assert result["query_type"] == "analytical"
        assert result["use_hyde"] is True
        assert result["multi_query_count"] == 3

    def test_should_parse_json_wrapped_in_plain_code_block(self):
        raw = '```\n{"needs_retrieval": false, "query_type": "factual"}\n```'
        result = _parse_classification(raw)
        assert result["needs_retrieval"] is False

    def test_should_use_defaults_for_invalid_json(self):
        raw = "this is not json at all"
        result = _parse_classification(raw)
        assert result["needs_retrieval"] is True
        assert result["query_type"] == "factual"
        assert result["use_hyde"] is False
        assert result["multi_query_count"] == 1

    def test_should_use_defaults_for_empty_string(self):
        result = _parse_classification("")
        assert result["needs_retrieval"] is True
        assert result["query_type"] == "factual"

    def test_should_normalize_invalid_query_type(self):
        """Unknown query_type values should fall back to 'factual'."""
        raw = '{"needs_retrieval": true, "query_type": "unknown_type"}'
        result = _parse_classification(raw)
        assert result["query_type"] == "factual"

    def test_should_handle_missing_fields_with_defaults(self):
        """Partial JSON should fill in defaults for missing fields."""
        raw = '{"query_type": "summary"}'
        result = _parse_classification(raw)
        assert result["needs_retrieval"] is True  # default
        assert result["query_type"] == "summary"
        assert result["use_hyde"] is False  # default
        assert result["multi_query_count"] == 1  # default

    @pytest.mark.parametrize("qtype", ["factual", "analytical", "multi_hop", "summary"])
    def test_should_accept_all_valid_query_types(self, qtype: str):
        raw = json.dumps({"needs_retrieval": True, "query_type": qtype})
        result = _parse_classification(raw)
        assert result["query_type"] == qtype


# ---------------------------------------------------------------------------
# classify_query (async, needs LLM mocking)
# ---------------------------------------------------------------------------


class TestClassifyQuery:
    """Test the async classify_query node with mocked LLM."""

    @pytest.fixture
    def mock_state(self):
        """Minimal AgentState for testing."""
        return {
            "query": "什么是RAG?",
            "kb_id": "test12345678",
            "messages": [],
            "retrieved_docs": [],
            "reasoning": "",
            "answer": "",
            "sources": [],
            "query_type": "",
            "needs_retrieval": True,
            "search_strategy": {},
            "original_query": "",
            "quality_score": 0.0,
            "verify_feedback": "",
            "needs_refine": False,
        }

    @pytest.mark.asyncio
    async def test_should_return_correct_structure(self, mock_state):
        """classify_query should return all required keys."""
        llm_response = AIMessage(content=_RESP_FACTUAL)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with patch("app.agent.nodes.query_classifier._get_llm", return_value=mock_llm):
            result = await classify_query(mock_state)

        assert "needs_retrieval" in result
        assert "query_type" in result
        assert "search_strategy" in result
        assert "original_query" in result
        assert "use_hyde" in result["search_strategy"]
        assert "multi_query_count" in result["search_strategy"]

    @pytest.mark.asyncio
    async def test_should_classify_factual_query(self, mock_state):
        mock_state["query"] = "什么是RAG?"
        llm_response = AIMessage(content=_RESP_FACTUAL)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with patch("app.agent.nodes.query_classifier._get_llm", return_value=mock_llm):
            result = await classify_query(mock_state)

        assert result["query_type"] == "factual"
        assert result["needs_retrieval"] is True
        assert result["search_strategy"]["use_hyde"] is False
        assert result["search_strategy"]["multi_query_count"] == 1

    @pytest.mark.asyncio
    async def test_should_classify_analytical_query(self, mock_state):
        mock_state["query"] = "比较RAG和Fine-tuning的优劣"
        llm_response = AIMessage(content=_RESP_ANALYTICAL)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with patch("app.agent.nodes.query_classifier._get_llm", return_value=mock_llm):
            result = await classify_query(mock_state)

        assert result["query_type"] == "analytical"
        assert result["search_strategy"]["use_hyde"] is True
        assert result["search_strategy"]["multi_query_count"] == 3

    @pytest.mark.asyncio
    async def test_should_use_defaults_on_llm_failure(self, mock_state):
        """When LLM raises an exception, classify_query should return safe defaults."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM service unavailable"))

        with patch("app.agent.nodes.query_classifier._get_llm", return_value=mock_llm):
            result = await classify_query(mock_state)

        assert result["needs_retrieval"] is True
        assert result["query_type"] == "factual"
        assert result["search_strategy"]["use_hyde"] is False
        assert result["search_strategy"]["multi_query_count"] == 1
        assert result["original_query"] == mock_state["query"]

    @pytest.mark.asyncio
    async def test_should_preserve_original_query(self, mock_state):
        """original_query in output should match the input query."""
        mock_state["query"] = "SEEDER和RAGAS有什么区别？"
        llm_response = AIMessage(content=_RESP_MULTI_HOP)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with patch("app.agent.nodes.query_classifier._get_llm", return_value=mock_llm):
            result = await classify_query(mock_state)

        assert result["original_query"] == "SEEDER和RAGAS有什么区别？"

    @pytest.mark.asyncio
    async def test_should_handle_empty_llm_response(self, mock_state):
        """Empty response content should trigger fallback defaults."""
        llm_response = AIMessage(content="")
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with patch("app.agent.nodes.query_classifier._get_llm", return_value=mock_llm):
            result = await classify_query(mock_state)

        assert result["query_type"] == "factual"
        assert result["needs_retrieval"] is True
