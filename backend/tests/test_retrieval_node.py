"""Unit tests for retrieval_node.py — Enhanced hybrid retrieval with HyDE and Multi-Query.

Covers:
- retrieval_node main flow (basic, HyDE, Multi-Query, combined, fallback)
- _generate_hyde (success, LLM failure)
- _generate_multi_queries (success, non-comma output, LLM failure, count <= 1)
- _multi_query_retrieve (single query, multi-query dedup, partial failure, full failure)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


def make_doc(
    chunk_id: str = "c1", content: str = "测试内容", score: float = 0.9, doc_id: str = "doc1"
) -> dict:
    """Create a mock retrieval document."""
    return {
        "chunk_id": chunk_id,
        "text": content,
        "score": score,
        "doc_id": doc_id,
        "kb_id": "test_kb",
    }


def make_state(
    query: str = "什么是机器学习？",
    kb_id: str = "test_kb_123",
    use_hyde: bool = False,
    multi_query_count: int = 1,
    query_type: str = "factual",
) -> dict:
    """Create a minimal AgentState dict for retrieval_node."""
    return {
        "messages": [HumanMessage(content=query)],
        "query": query,
        "kb_id": kb_id,
        "search_strategy": {
            "use_hyde": use_hyde,
            "multi_query_count": multi_query_count,
        },
        "query_type": query_type,
        "verification": None,
        "retrieved_docs": [],
        "sources": [],
        "reasoning": "",
        "answer": "",
        "needs_retrieval": True,
        "original_query": query,
        "quality_score": 0.0,
        "verify_feedback": "",
        "needs_refine": False,
    }


# ---------------------------------------------------------------------------
# _generate_hyde tests
# ---------------------------------------------------------------------------


class TestGenerateHyde:
    """Tests for the HyDE hypothetical document generation."""

    async def test_should_return_hypothetical_document_when_llm_succeeds(self):
        """Normal case: LLM returns a hypothetical answer."""
        from app.agent.nodes.retrieval_node import _generate_hyde

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(
            content="机器学习是人工智能的一个分支。它通过数据驱动的方式学习模式。"
        )

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_hyde("什么是机器学习？")

        assert "机器学习" in result
        mock_llm.ainvoke.assert_awaited_once()

    async def test_should_return_original_query_when_llm_fails(self):
        """Fallback: LLM call raises exception, return original query."""
        from app.agent.nodes.retrieval_node import _generate_hyde

        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("LLM service unavailable")

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_hyde("什么是机器学习？")

        assert result == "什么是机器学习？"

    async def test_should_strip_whitespace_from_response(self):
        """HyDE output should be stripped of leading/trailing whitespace."""
        from app.agent.nodes.retrieval_node import _generate_hyde

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="  假设性答案  ")

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_hyde("测试查询")

        assert result == "假设性答案"

    async def test_should_handle_empty_llm_response(self):
        """When LLM returns empty content, should return empty string."""
        from app.agent.nodes.retrieval_node import _generate_hyde

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="")

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_hyde("测试查询")

        assert result == ""

    async def test_should_handle_none_content_in_response(self):
        """When LLM returns None content, should fall back to empty string."""
        from app.agent.nodes.retrieval_node import _generate_hyde

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = None
        mock_llm.ainvoke.return_value = mock_response

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_hyde("测试查询")

        assert result == ""


# ---------------------------------------------------------------------------
# _generate_multi_queries tests
# ---------------------------------------------------------------------------


class TestGenerateMultiQueries:
    """Tests for multi-query generation."""

    async def test_should_return_single_query_when_count_is_one(self):
        """When count <= 1, return the original query without calling LLM."""
        from app.agent.nodes.retrieval_node import _generate_multi_queries

        with patch("app.agent.nodes.retrieval_node._get_llm") as mock_get_llm:
            result = await _generate_multi_queries("什么是机器学习？", count=1)

        assert result == ["什么是机器学习？"]
        mock_get_llm.assert_not_called()

    async def test_should_return_single_query_when_count_is_zero(self):
        """When count is 0, return the original query."""
        from app.agent.nodes.retrieval_node import _generate_multi_queries

        with patch("app.agent.nodes.retrieval_node._get_llm") as mock_get_llm:
            result = await _generate_multi_queries("什么是机器学习？", count=0)

        assert result == ["什么是机器学习？"]
        mock_get_llm.assert_not_called()

    async def test_should_generate_query_variants_when_llm_succeeds(self):
        """Normal case: LLM returns newline-separated query variants."""
        from app.agent.nodes.retrieval_node import _generate_multi_queries

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(
            content="机器学习的定义是什么？\n机器学习有哪些类型？"
        )

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_multi_queries("什么是机器学习？", count=3)

        assert len(result) == 3
        assert result[0] == "什么是机器学习？"  # original query first
        assert "机器学习的定义是什么？" in result
        assert "机器学习有哪些类型？" in result

    async def test_should_limit_variants_to_count_minus_one(self):
        """Should only include up to count-1 variants from LLM output."""
        from app.agent.nodes.retrieval_node import _generate_multi_queries

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="变体1\n变体2\n变体3\n变体4\n变体5")

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_multi_queries("原始查询", count=3)

        # 1 original + 2 variants (count-1)
        assert len(result) == 3
        assert result[0] == "原始查询"

    async def test_should_return_original_query_when_llm_fails(self):
        """Fallback: LLM call raises exception, return original query."""
        from app.agent.nodes.retrieval_node import _generate_multi_queries

        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("LLM timeout")

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_multi_queries("什么是机器学习？", count=3)

        assert result == ["什么是机器学习？"]

    async def test_should_filter_empty_lines_from_llm_output(self):
        """Empty lines in LLM output should be filtered out."""
        from app.agent.nodes.retrieval_node import _generate_multi_queries

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="变体1\n\n  \n变体2\n")

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_multi_queries("原始查询", count=3)

        assert len(result) == 3  # original + 2 non-empty variants
        assert result[0] == "原始查询"

    async def test_should_handle_empty_llm_response(self):
        """When LLM returns empty content, should return only original query."""
        from app.agent.nodes.retrieval_node import _generate_multi_queries

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="")

        with patch("app.agent.nodes.retrieval_node._get_llm", return_value=mock_llm):
            result = await _generate_multi_queries("原始查询", count=3)

        # Only original query, no variants parsed from empty string
        assert result == ["原始查询"]


# ---------------------------------------------------------------------------
# _multi_query_retrieve tests
# ---------------------------------------------------------------------------


class TestMultiQueryRetrieve:
    """Tests for multi-query retrieval with deduplication."""

    async def test_should_return_dense_and_sparse_for_single_query(self):
        """Single query: standard dense + sparse retrieval."""
        from app.agent.nodes.retrieval_node import _multi_query_retrieve

        dense_docs = [make_doc("c1", "dense1", 0.9)]
        sparse_docs = [make_doc("c2", "sparse1", 0.8)]

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=dense_docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=sparse_docs),
        ):
            d_results, s_results = await _multi_query_retrieve(
                ["什么是机器学习？"],
                "test_kb",
                use_hyde=False,
            )

        assert len(d_results) == 1
        assert len(s_results) == 1
        assert d_results[0]["chunk_id"] == "c1"
        assert s_results[0]["chunk_id"] == "c2"

    async def test_should_deduplicate_by_chunk_id_across_queries(self):
        """Multi-query: docs with same chunk_id should be deduplicated."""
        from app.agent.nodes.retrieval_node import _multi_query_retrieve

        # Two queries return overlapping chunk_ids
        dense_q1 = [make_doc("c1", "content1", 0.8), make_doc("c2", "content2", 0.7)]
        dense_q2 = [make_doc("c1", "content1", 0.9), make_doc("c3", "content3", 0.6)]
        sparse_q1 = [make_doc("c4", "sparse1", 0.5)]
        sparse_q2 = [make_doc("c4", "sparse2", 0.6)]

        call_count = 0

        async def mock_dense_search(q_emb, kb_id, k=50):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # first two calls are dense (one per query)
                return dense_q1 if call_count == 1 else dense_q2
            return []

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch("app.agent.nodes.retrieval_node.dense.search", side_effect=mock_dense_search),
            patch(
                "app.agent.nodes.retrieval_node.sparse.search", side_effect=[sparse_q1, sparse_q2]
            ),
        ):
            d_results, s_results = await _multi_query_retrieve(
                ["q1", "q2"],
                "test_kb",
                use_hyde=False,
                k_per_query=30,
            )

        # c1 appears twice in dense, should keep the one with higher score (0.9)
        c1_docs = [d for d in d_results if d["chunk_id"] == "c1"]
        assert len(c1_docs) == 1
        assert c1_docs[0]["score"] == 0.9

        # c2 and c3 should both be present
        chunk_ids = {d["chunk_id"] for d in d_results}
        assert "c2" in chunk_ids
        assert "c3" in chunk_ids

        # c4 deduplicated in sparse
        c4_docs = [d for d in s_results if d["chunk_id"] == "c4"]
        assert len(c4_docs) == 1
        assert c4_docs[0]["score"] == 0.6

    async def test_should_skip_failed_retrieve_in_multi_query(self):
        """When some retrieval tasks fail, should return only successful results."""
        from app.agent.nodes.retrieval_node import _multi_query_retrieve

        good_docs = [make_doc("c1", "good", 0.9)]

        async def mock_dense_search(q_emb, kb_id, k=50):
            # First query succeeds, second fails
            if q_emb == [0.1] * 1024:
                return good_docs
            raise RuntimeError("Embedding service down")

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch("app.agent.nodes.retrieval_node.dense.search", side_effect=mock_dense_search),
            patch(
                "app.agent.nodes.retrieval_node.sparse.search",
                side_effect=[good_docs, RuntimeError("fail")],
            ),
        ):
            d_results, s_results = await _multi_query_retrieve(
                ["q1", "q2"],
                "test_kb",
                use_hyde=False,
                k_per_query=30,
            )

        # Should still have results from the successful query
        assert len(d_results) >= 1
        assert len(s_results) >= 1

    async def test_should_return_empty_when_all_retrievals_fail(self):
        """When all retrieval tasks fail, should return empty lists."""
        from app.agent.nodes.retrieval_node import _multi_query_retrieve

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                side_effect=RuntimeError("fail"),
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", side_effect=RuntimeError("fail")),
        ):
            d_results, s_results = await _multi_query_retrieve(
                ["q1", "q2"],
                "test_kb",
                use_hyde=False,
                k_per_query=30,
            )

        assert d_results == []
        assert s_results == []

    async def test_should_use_hyde_for_first_query_only(self):
        """When use_hyde=True and multiple queries, HyDE should only apply to first query."""
        from app.agent.nodes.retrieval_node import _multi_query_retrieve

        mock_hyde = AsyncMock(return_value="假设性文档")
        docs = [make_doc("c1", "content", 0.9)]

        with (
            patch("app.agent.nodes.retrieval_node._generate_hyde", mock_hyde),
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
        ):
            await _multi_query_retrieve(
                ["q1", "q2"],
                "test_kb",
                use_hyde=True,
                k_per_query=30,
            )

        # HyDE should be called only once (for the first query)
        mock_hyde.assert_awaited_once_with("q1")


# ---------------------------------------------------------------------------
# retrieval_node main flow tests
# ---------------------------------------------------------------------------


class TestRetrievalNode:
    """Tests for the main retrieval_node function."""

    async def test_should_return_sources_and_messages_for_basic_retrieval(self):
        """Basic retrieval (no HyDE, no Multi-Query) should return sources and empty messages."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state(use_hyde=False, multi_query_count=1)
        dense_docs = [make_doc("c1", "内容1", 0.9), make_doc("c2", "内容2", 0.8)]
        sparse_docs = [make_doc("c3", "内容3", 0.7)]
        fused_docs = [
            make_doc("c1", "内容1", 0.95),
            make_doc("c2", "内容2", 0.85),
            make_doc("c3", "内容3", 0.75),
        ]
        reranked_docs = [make_doc("c1", "内容1", 0.98), make_doc("c2", "内容2", 0.88)]

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=dense_docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=sparse_docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=fused_docs),
            patch(
                "app.retrieval.reranker.rerank", new_callable=AsyncMock, return_value=reranked_docs
            ),
        ):
            result = await retrieval_node(state)

        assert "retrieved_docs" in result
        assert "messages" in result
        assert len(result["retrieved_docs"]) == 2
        assert result["messages"] == []

    async def test_should_use_hyde_when_strategy_enabled(self):
        """When search_strategy.use_hyde=True, should call _generate_hyde."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state(use_hyde=True, multi_query_count=1)
        docs = [make_doc("c1", "内容", 0.9)]

        mock_hyde = AsyncMock(return_value="假设性文档内容")

        with (
            patch("app.agent.nodes.retrieval_node._generate_hyde", mock_hyde),
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=docs),
            patch("app.retrieval.reranker.rerank", new_callable=AsyncMock, return_value=docs),
        ):
            result = await retrieval_node(state)

        mock_hyde.assert_awaited_once_with("什么是机器学习？")
        assert len(result["retrieved_docs"]) == 1

    async def test_should_generate_multi_queries_when_count_gt_1(self):
        """When multi_query_count > 1, should call _generate_multi_queries."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state(use_hyde=False, multi_query_count=3)
        docs = [make_doc("c1", "内容", 0.9)]

        mock_multi = AsyncMock(return_value=["q1", "q2", "q3"])

        with (
            patch("app.agent.nodes.retrieval_node._generate_multi_queries", mock_multi),
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=docs),
            patch("app.retrieval.reranker.rerank", new_callable=AsyncMock, return_value=docs),
        ):
            result = await retrieval_node(state)

        mock_multi.assert_awaited_once_with("什么是机器学习？", 3)
        assert len(result["retrieved_docs"]) == 1

    async def test_should_use_hyde_and_multi_query_together(self):
        """When both HyDE and Multi-Query enabled, both should be invoked."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state(use_hyde=True, multi_query_count=3)
        docs = [make_doc("c1", "内容", 0.9)]

        mock_multi = AsyncMock(return_value=["q1", "q2", "q3"])
        mock_hyde = AsyncMock(return_value="假设性文档")

        with (
            patch("app.agent.nodes.retrieval_node._generate_multi_queries", mock_multi),
            patch("app.agent.nodes.retrieval_node._generate_hyde", mock_hyde),
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=docs),
            patch("app.retrieval.reranker.rerank", new_callable=AsyncMock, return_value=docs),
        ):
            result = await retrieval_node(state)

        mock_multi.assert_awaited_once()
        # HyDE is called inside _multi_query_retrieve, not directly by retrieval_node
        assert len(result["retrieved_docs"]) == 1

    async def test_should_return_empty_docs_when_no_query(self):
        """When query is empty, should return empty results immediately."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state(query="", kb_id="test_kb")

        result = await retrieval_node(state)

        assert result["retrieved_docs"] == []
        assert result["messages"] == []

    async def test_should_return_empty_docs_when_no_kb_id(self):
        """When kb_id is empty, should return empty results immediately."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state(query="什么是机器学习？", kb_id="")

        result = await retrieval_node(state)

        assert result["retrieved_docs"] == []
        assert result["messages"] == []

    async def test_should_use_default_strategy_when_missing(self):
        """When search_strategy is missing, should use defaults (no HyDE, single query)."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state()
        del state["search_strategy"]  # Remove strategy entirely

        docs = [make_doc("c1", "内容", 0.9)]

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=docs),
            patch("app.retrieval.reranker.rerank", new_callable=AsyncMock, return_value=docs),
        ):
            result = await retrieval_node(state)

        assert len(result["retrieved_docs"]) == 1

    async def test_should_call_rrf_fusion_with_dense_and_sparse_results(self):
        """rrf_fusion should receive the dense and sparse results from retrieval."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state()
        dense_docs = [make_doc("c1", "dense", 0.9)]
        sparse_docs = [make_doc("c2", "sparse", 0.8)]
        fused = [make_doc("c1", "dense", 0.95), make_doc("c2", "sparse", 0.85)]

        mock_rrf = MagicMock(return_value=fused)

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=dense_docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=sparse_docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", mock_rrf),
            patch("app.retrieval.reranker.rerank", new_callable=AsyncMock, return_value=fused),
        ):
            await retrieval_node(state)

        mock_rrf.assert_called_once_with(dense_docs, sparse_docs, top_n=15)

    async def test_should_call_rerank_with_query_and_fused_docs(self):
        """rerank should receive the query and fused documents with query-type-aware top_n."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state(query="测试查询")
        docs = [make_doc("c1", "内容", 0.9)]
        fused = [make_doc("c1", "内容", 0.95)]

        mock_rerank = AsyncMock(return_value=docs)

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=fused),
            patch("app.retrieval.reranker.rerank", mock_rerank),
        ):
            await retrieval_node(state)

        mock_rerank.assert_awaited_once_with("测试查询", fused, top_n=5)

    async def test_should_handle_rerank_failure_gracefully(self):
        """When rerank raises an exception, retrieval_node should propagate it (or handle)."""
        from app.agent.nodes.retrieval_node import retrieval_node

        state = make_state()
        docs = [make_doc("c1", "内容", 0.9)]

        with (
            patch(
                "app.agent.nodes.retrieval_node._embed_query_with_cache",
                new_callable=AsyncMock,
                return_value=[0.1] * 1024,
            ),
            patch(
                "app.agent.nodes.retrieval_node.dense.search",
                new_callable=AsyncMock,
                return_value=docs,
            ),
            patch("app.agent.nodes.retrieval_node.sparse.search", return_value=docs),
            patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion", return_value=docs),
            patch(
                "app.retrieval.reranker.rerank",
                new_callable=AsyncMock,
                side_effect=RuntimeError("reranker crash"),
            ),
        ):
            with pytest.raises(RuntimeError, match="reranker crash"):
                await retrieval_node(state)


# ---------------------------------------------------------------------------
# _dense_search_with_hyde tests
# ---------------------------------------------------------------------------


class TestDenseSearchWithHyde:
    """Tests for the _dense_search_with_hyde helper."""

    async def test_should_use_hyde_embedding_when_enabled(self):
        """When use_hyde=True, should generate HyDE doc and embed it."""
        from app.agent.nodes.retrieval_node import _dense_search_with_hyde

        mock_hyde = AsyncMock(return_value="假设性文档")
        mock_embed = AsyncMock(return_value=[0.2] * 1024)
        mock_search = AsyncMock(return_value=[make_doc("c1", "内容", 0.9)])

        with (
            patch("app.agent.nodes.retrieval_node._generate_hyde", mock_hyde),
            patch("app.agent.nodes.retrieval_node._embed_query_with_cache", mock_embed),
            patch("app.agent.nodes.retrieval_node.dense.search", mock_search),
        ):
            result = await _dense_search_with_hyde("原始查询", "test_kb", use_hyde=True, k=50)

        mock_hyde.assert_awaited_once_with("原始查询")
        mock_embed.assert_awaited_once_with("假设性文档")
        assert len(result) == 1

    async def test_should_embed_original_query_when_hyde_disabled(self):
        """When use_hyde=False, should embed the original query directly."""
        from app.agent.nodes.retrieval_node import _dense_search_with_hyde

        mock_embed = AsyncMock(return_value=[0.2] * 1024)
        mock_search = AsyncMock(return_value=[make_doc("c1", "内容", 0.9)])

        with (
            patch("app.agent.nodes.retrieval_node._embed_query_with_cache", mock_embed),
            patch("app.agent.nodes.retrieval_node.dense.search", mock_search),
        ):
            result = await _dense_search_with_hyde("原始查询", "test_kb", use_hyde=False, k=50)

        mock_embed.assert_awaited_once_with("原始查询")
        assert len(result) == 1
