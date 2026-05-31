"""Tests for evaluation module (R7)."""
import json
from pathlib import Path

import pytest
from app.evaluation.cli import Evaluator


@pytest.fixture
def sample_test_cases(tmp_path: Path) -> str:
    cases = [
        {"query": "什么是混合检索？", "expected": "向量检索+关键词检索"},
        {"query": "LangGraph是什么？", "expected": "图编排框架"},
    ]
    path = tmp_path / "test_cases.json"
    with open(path, "w") as f:
        json.dump(cases, f)
    return str(path)


class TestEvaluator:
    """R7: CLI evaluation."""

    def test_load_json_cases(self, sample_test_cases: str):
        """Should load JSON test cases correctly."""
        evaluator = Evaluator("test_kb", sample_test_cases, "/tmp/test_out.json")
        cases = evaluator.load_test_cases()
        assert len(cases) == 2
        assert cases[0]["query"] == "什么是混合检索？"

    def test_metrics_correctness(self):
        """Correctness metric should measure keyword overlap."""
        evaluator = Evaluator("test_kb", "", "/tmp/test_out.json")
        metrics = evaluator._compute_metrics(
            "混合检索是什么",
            "混合检索结合向量和关键词",
            "混合检索结合向量和关键词两种方法",
            [{"score": 0.8, "chunk_id": "c1", "text": "混合检索是..."}],
        )
        assert 0 <= metrics["correctness"] <= 1
        assert 0 <= metrics["groundedness"] <= 1
        assert 0 <= metrics["retrieval_relevance"] <= 1

    def test_metrics_no_expected(self):
        """Should handle missing expected answer."""
        evaluator = Evaluator("test_kb", "", "/tmp/test_out.json")
        metrics = evaluator._compute_metrics(
            "测试查询",
            "",
            "这是一个回答",
            [],
        )
        assert metrics["correctness"] == 0.0
        assert metrics["groundedness"] == 0.0

    def test_metrics_no_retrieved(self):
        """Should handle empty retrieved docs."""
        evaluator = Evaluator("test_kb", "", "/tmp/test_out.json")
        metrics = evaluator._compute_metrics(
            "测试查询",
            "预期答案",
            "实际答案",
            [],
        )
        assert metrics["groundedness"] == 0.0
        assert metrics["retrieval_relevance"] == 0.0
