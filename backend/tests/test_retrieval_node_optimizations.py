"""Optimization verification tests for retrieval_node.py.

This test suite validates the three key optimizations applied to the
retrieval node:

1. **Dynamic retrieval config** — RETRIEVAL_CONFIG maps query_type to
   (rerank_top_k, k_per_query, fusion_top_n) so each query type gets an
   appropriate amount of context.

2. **Embedding LRU cache** — identical query texts are embedded only once,
   reducing API calls and latency.

3. **Consistent k_per_query** — the single-query path uses k_per_query
   instead of the previously hardcoded k=50.

See :mod:`app.agent.nodes.retrieval_node` for the implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.nodes.retrieval_node import RETRIEVAL_CONFIG

# ---------------------------------------------------------------------------
# Test 1: RETRIEVAL_CONFIG structure and completeness
# ---------------------------------------------------------------------------


class TestRetrievalConfigStructure:
    """Validate that RETRIEVAL_CONFIG is complete and internally consistent."""

    def test_config_contains_all_expected_query_types(self):
        """All query types plus a fallback default must be present."""
        expected_keys = {"factual", "analytical", "multi_hop", "summary", "default"}
        assert expected_keys.issubset(RETRIEVAL_CONFIG.keys())

    def test_each_config_has_all_three_parameters(self):
        """Every config entry must define rerank_top_k, k_per_query, fusion_top_n."""
        required_params = {"rerank_top_k", "k_per_query", "fusion_top_n"}
        for qtype, cfg in RETRIEVAL_CONFIG.items():
            assert required_params.issubset(cfg.keys()), f"{qtype} missing params"

    def test_all_parameters_are_positive_integers(self):
        """Every parameter value must be a positive integer."""
        for qtype, cfg in RETRIEVAL_CONFIG.items():
            for key, val in cfg.items():
                assert isinstance(val, int) and val > 0, (
                    f"{qtype}.{key}={val!r} is not a positive int"
                )

    def test_coverage_increases_from_factual_to_summary(self):
        """Coverage should monotonically increase: factual ≤ analytical ≤ multi_hop ≤ summary."""
        for param in ("rerank_top_k", "k_per_query", "fusion_top_n"):
            vals = {
                q: RETRIEVAL_CONFIG[q][param]
                for q in ("factual", "analytical", "multi_hop", "summary")
            }
            assert vals["factual"] <= vals["analytical"], f"{param}: factual > analytical"
            assert vals["analytical"] <= vals["multi_hop"], f"{param}: analytical > multi_hop"
            # Allow multi_hop == summary or summary > multi_hop
            assert vals["multi_hop"] <= vals["summary"], f"{param}: multi_hop > summary"

    def test_config_values_are_within_reasonable_range(self):
        """Sanity-check: parameters must not be extreme."""
        for cfg in RETRIEVAL_CONFIG.values():
            assert 1 <= cfg["rerank_top_k"] <= 20, "rerank_top_k out of [1, 20]"
            assert 5 <= cfg["k_per_query"] <= 100, "k_per_query out of [5, 100]"
            assert 5 <= cfg["fusion_top_n"] <= 100, "fusion_top_n out of [5, 100]"

    def test_default_is_at_least_factual(self):
        """Default coverage should be >= factual (safe fallback)."""
        default = RETRIEVAL_CONFIG["default"]
        factual = RETRIEVAL_CONFIG["factual"]
        for param in ("rerank_top_k", "k_per_query", "fusion_top_n"):
            assert default[param] >= factual[param], (
                f"default.{param} < factual.{param}"
            )


# ---------------------------------------------------------------------------
# Test 2: Dynamic config selection in retrieval_node
# ---------------------------------------------------------------------------


class TestRetrievalNodeDynamicConfig:
    """Verify that retrieval_node selects config based on query_type."""

    @pytest.fixture
    def state_template(self):
        return {
            "messages": [],
            "query": "test query",
            "kb_id": "test_kb",
            "search_strategy": {"use_hyde": False, "multi_query_count": 1},
            "retrieved_docs": [],
            "sources": [],
            "reasoning": "",
            "answer": "",
            "needs_retrieval": True,
            "original_query": "test query",
            "quality_score": 0.0,
            "verify_feedback": "",
            "needs_refine": False,
        }

    async def _run_retrieval_with_type(self, query_type: str, state_template: dict):
        """Run retrieval_node with a specific query_type and return the mock call args."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = dict(state_template, query_type=query_type)
        docs = [{"chunk_id": "c1", "text": "test", "score": 0.9}]

        # Capture the actual config used via the rerank mock
        mock_rerank = AsyncMock(return_value=docs)

        with (
            patch("app.agent.nodes.retrieval_node._embed_query_with_cache", new_callable=AsyncMock, return_value=[0.1] * 1024),
            patch("app.agent.nodes.retrieval_node.dense.search", new_callable=AsyncMock, return_value=docs),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=docs),
            patch("app.retrieval.reranker.rerank", mock_rerank),
        ):
            await retrieval_node(state)

        return mock_rerank

    @pytest.mark.asyncio
    async def test_factual_uses_smallest_rerank_top_k(self, state_template):
        """Factual queries should use rerank_top_k=5 (tolerance for missing docs)."""
        mock_rerank = await self._run_retrieval_with_type("factual", state_template)
        call_kwargs = mock_rerank.await_args
        assert call_kwargs is not None
        assert call_kwargs[1]["top_n"] == 5

    @pytest.mark.asyncio
    async def test_summary_uses_largest_rerank_top_k(self, state_template):
        """Summary queries should use rerank_top_k=10 (broad coverage)."""
        mock_rerank = await self._run_retrieval_with_type("summary", state_template)
        call_kwargs = mock_rerank.await_args
        assert call_kwargs is not None
        assert call_kwargs[1]["top_n"] == 10

    @pytest.mark.asyncio
    async def test_analytical_uses_moderate_rerank_top_k(self, state_template):
        """Analytical queries should use rerank_top_k=5."""
        mock_rerank = await self._run_retrieval_with_type("analytical", state_template)
        call_kwargs = mock_rerank.await_args
        assert call_kwargs is not None
        assert call_kwargs[1]["top_n"] == 5

    @pytest.mark.asyncio
    async def test_multi_hop_uses_high_rerank_top_k(self, state_template):
        """Multi-hop queries should use rerank_top_k=8."""
        mock_rerank = await self._run_retrieval_with_type("multi_hop", state_template)
        call_kwargs = mock_rerank.await_args
        assert call_kwargs is not None
        assert call_kwargs[1]["top_n"] == 8

    @pytest.mark.asyncio
    async def test_unknown_query_type_falls_back_to_default(self, state_template):
        """Unknown query_type should fallback to default config (rerank_top_k=5)."""
        mock_rerank = await self._run_retrieval_with_type("unknown_type", state_template)
        call_kwargs = mock_rerank.await_args
        assert call_kwargs is not None
        assert call_kwargs[1]["top_n"] == 5

    @pytest.mark.asyncio
    async def test_missing_query_type_uses_default(self, state_template):
        """When query_type is missing from state, should use default config."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = dict(state_template)
        # Deliberately remove query_type
        state.pop("query_type", None)
        docs = [{"chunk_id": "c1", "text": "test", "score": 0.9}]

        mock_rerank = AsyncMock(return_value=docs)
        with (
            patch("app.agent.nodes.retrieval_node._embed_query_with_cache", new_callable=AsyncMock, return_value=[0.1] * 1024),
            patch("app.agent.nodes.retrieval_node.dense.search", new_callable=AsyncMock, return_value=docs),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=docs),
            patch("app.retrieval.reranker.rerank", mock_rerank),
        ):
            await retrieval_node(state)

        call_kwargs = mock_rerank.await_args
        assert call_kwargs is not None
        assert call_kwargs[1]["top_n"] == 5  # default.rerank_top_k


# ---------------------------------------------------------------------------
# Test 3: Embedding LRU cache
# ---------------------------------------------------------------------------


class TestEmbeddingCache:
    """Verify that _cached_embed_query deduplicates identical texts."""

    def test_cache_returns_same_object_for_identical_text(self):
        """Calling _cached_embed_query twice with the same text should return
        the exact same list object (cache hit)."""
        from app.agent.nodes.retrieval_node import _cached_embed_query

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1, 0.2, 0.3]

        with patch("app.document.embedder.get_embedder", return_value=mock_embedder):
            result_1 = _cached_embed_query("hello world")
            result_2 = _cached_embed_query("hello world")

        # Same text → only one call to embed_query
        assert mock_embedder.embed_query.call_count == 1
        # Results are the same object (from lru_cache)
        assert result_1 is result_2

    def test_cache_misses_for_different_texts(self):
        """Different texts should each call embed_query once."""
        from app.agent.nodes.retrieval_node import _cached_embed_query

        mock_embedder = MagicMock()
        mock_embedder.embed_query.side_effect = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]

        with patch("app.document.embedder.get_embedder", return_value=mock_embedder):
            _cached_embed_query("text A")
            _cached_embed_query("text B")

        # Different texts → two calls
        assert mock_embedder.embed_query.call_count == 2

    def test_cache_size_limit(self):
        """LRU cache should respect maxsize and evict oldest entries."""
        from app.agent.nodes.retrieval_node import _cached_embed_query

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1, 0.2, 0.3]

        with patch("app.document.embedder.get_embedder", return_value=mock_embedder):
            # Insert 150 unique entries (maxsize=128)
            for i in range(150):
                _cached_embed_query(f"unique text {i}")

            # First 22 entries should have been evicted
            # (lru_cache with maxsize=128 evicts least recently used)
            call_count_before = mock_embedder.embed_query.call_count

            # Access the first entry again — it was evicted, must re-compute
            _cached_embed_query("unique text 0")
            assert mock_embedder.embed_query.call_count == call_count_before + 1

            # But entry #149 is still in cache
            _cached_embed_query("unique text 149")
            assert mock_embedder.embed_query.call_count == call_count_before + 1  # no new call


# ---------------------------------------------------------------------------
# Test 4: _embed_query_with_cache integration with _dense_search_with_hyde
# ---------------------------------------------------------------------------


class TestEmbedQueryWithCacheIntegration:
    """Verify that _dense_search_with_hyde uses the cached embedding."""

    @pytest.mark.asyncio
    async def test_no_hyde_uses_cache(self):
        """Without HyDE, the original query should be cached via _embed_query_with_cache."""
        from app.agent.nodes.retrieval_node import _dense_search_with_hyde

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1, 0.2, 0.3],
            ) as mock_cache_embed,
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await _dense_search_with_hyde("test query", "kb_123", use_hyde=False, k=20)

        mock_cache_embed.assert_awaited_once_with("test query")

    @pytest.mark.asyncio
    async def test_with_hyde_generates_then_caches(self):
        """With HyDE, the hypothetical doc should be generated then cached."""
        from app.agent.nodes.retrieval_node import _dense_search_with_hyde

        with (
            patch(
                "app.agent.nodes.retrieval_node._generate_hyde",
                new_callable=AsyncMock,
                return_value="hypothetical doc",
            ),
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1, 0.2, 0.3],
            ) as mock_cache_embed,
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await _dense_search_with_hyde("test query", "kb_123", use_hyde=True, k=20)

        # Should embed the hypothetical doc, not the original query
        mock_cache_embed.assert_awaited_once_with("hypothetical doc")


# ---------------------------------------------------------------------------
# Test 5: Single-query path uses k_per_query instead of hardcoded 50
# ---------------------------------------------------------------------------


class TestSingleQueryKPerQuery:
    """Verify the single-query path respects k_per_query."""

    @pytest.mark.asyncio
    async def test_single_query_passes_k_per_query_to_dense_search(self):
        """Single query should pass k=k_per_query to _dense_search_with_hyde (not k=50)."""
        from app.agent.nodes.retrieval_node import _multi_query_retrieve

        custom_k = 42

        with (
            patch(
                "app.agent.nodes.retrieval_node._dense_search_with_hyde",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_dense,
            patch(
                "app.agent.nodes.retrieval_node.sparse.search",
                return_value=[],
            ) as mock_sparse,
        ):
            await _multi_query_retrieve(
                ["single query"],
                "kb_123",
                use_hyde=False,
                k_per_query=custom_k,
            )

        # Dense search should receive k=custom_k, not the old default of 50
        mock_dense.assert_awaited_once()
        call_kwargs = mock_dense.await_args
        assert call_kwargs is not None
        assert call_kwargs[1]["k"] == custom_k

        # Sparse search should also receive k=custom_k
        mock_sparse.assert_called_once()
        _, call_kwargs_sparse = mock_sparse.call_args
        assert call_kwargs_sparse["k"] == custom_k

    @pytest.mark.asyncio
    async def test_single_query_not_affected_by_hardcoded_50(self):
        """Even when use_hyde=True, single query uses k_per_query, not 50."""
        from app.agent.nodes.retrieval_node import _multi_query_retrieve

        custom_k = 15

        with (
            patch(
                "app.agent.nodes.retrieval_node._dense_search_with_hyde",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_dense,
            patch(
                "app.agent.nodes.retrieval_node.sparse.search",
                return_value=[],
            ),
        ):
            await _multi_query_retrieve(
                ["single query"],
                "kb_123",
                use_hyde=True,
                k_per_query=custom_k,
            )

        mock_dense.assert_awaited_once()
        call_kwargs = mock_dense.await_args
        assert call_kwargs is not None
        assert call_kwargs[1]["k"] == custom_k


# ---------------------------------------------------------------------------
# Test 6: Multi-query path also respects k_per_query
# ---------------------------------------------------------------------------


class TestMultiQueryKPerQuery:
    """Verify the multi-query path also respects k_per_query."""

    @pytest.mark.asyncio
    async def test_multi_query_passes_k_per_query_to_all_searches(self):
        """Each variant query should use k_per_query, not hardcoded 50."""
        from app.agent.nodes.retrieval_node import _multi_query_retrieve

        custom_k = 25

        with (
            patch(
                "app.agent.nodes.retrieval_node._generate_hyde",
                new_callable=AsyncMock,
                return_value="hypo",
            ),
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.agent.nodes.retrieval_node.sparse.search",
                return_value=[],
            ) as mock_sparse,
        ):
            await _multi_query_retrieve(
                ["q1", "q2", "q3"],
                "kb_123",
                use_hyde=False,
                k_per_query=custom_k,
            )

        # Sparse search should be called 3 times, each with k=custom_k
        assert mock_sparse.call_count == 3
        for call_args in mock_sparse.call_args_list:
            _, kwargs = call_args
            assert kwargs["k"] == custom_k
