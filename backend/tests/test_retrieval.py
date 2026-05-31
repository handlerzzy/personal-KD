"""Tests for retrieval module (R3)."""
from app.retrieval.hybrid import rrf_fusion


class TestRRFFusion:
    """R3: RRF fusion algorithm."""

    def test_empty_results(self):
        """RRF should handle empty inputs."""
        result = rrf_fusion([], [], top_n=10)
        assert result == []

    def test_only_dense(self):
        """RRF should work with only dense results."""
        dense = [
            {"chunk_id": "a", "text": "doc a", "score": 0.9, "doc_id": "", "kb_id": ""},
            {"chunk_id": "b", "text": "doc b", "score": 0.8, "doc_id": "", "kb_id": ""},
        ]
        result = rrf_fusion(dense, [], top_n=10)
        assert len(result) == 2
        assert result[0]["chunk_id"] == "a"
        assert result[0]["score"] > result[1]["score"]

    def test_only_sparse(self):
        """RRF should work with only sparse results."""
        sparse = [
            {"chunk_id": "x", "text": "doc x", "score": 0.7, "doc_id": "", "kb_id": ""},
        ]
        result = rrf_fusion([], sparse, top_n=10)
        assert len(result) == 1
        assert result[0]["chunk_id"] == "x"

    def test_rrf_ranking(self):
        """RRF should boost documents appearing in both lists."""
        dense = [
            {"chunk_id": "a", "text": "doc a", "score": 0.9, "doc_id": "", "kb_id": ""},
            {"chunk_id": "b", "text": "doc b", "score": 0.8, "doc_id": "", "kb_id": ""},
        ]
        sparse = [
            {"chunk_id": "b", "text": "doc b", "score": 0.7, "doc_id": "", "kb_id": ""},
            {"chunk_id": "c", "text": "doc c", "score": 0.6, "doc_id": "", "kb_id": ""},
        ]
        result = rrf_fusion(dense, sparse, top_n=10)
        assert len(result) == 3
        # 'b' appears in both lists, should rank first
        assert result[0]["chunk_id"] == "b"

    def test_top_n_limit(self):
        """RRF should respect top_n limit."""
        dense = [
            {"chunk_id": f"d{i}", "text": f"doc {i}", "score": 1.0 - i * 0.1,
             "doc_id": "", "kb_id": ""}
            for i in range(20)
        ]
        result = rrf_fusion(dense, [], top_n=5)
        assert len(result) == 5

    def test_rrf_score_range(self):
        """RRF scores should be positive and finite."""
        dense = [
            {"chunk_id": "a", "text": "doc a", "score": 0.9, "doc_id": "", "kb_id": ""},
        ]
        sparse = [
            {"chunk_id": "a", "text": "doc a", "score": 0.7, "doc_id": "", "kb_id": ""},
        ]
        result = rrf_fusion(dense, sparse, top_n=10)
        assert result[0]["score"] > 0
        assert result[0]["score"] < 2  # max possible: 1/61 + 1/61 ≈ 0.033
