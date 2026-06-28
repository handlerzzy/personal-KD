"""Configuration validation tests for query_type grading system.

Validates that the multi-layered per-type configurations across all agent
nodes are internally consistent, properly ordered by intensity, and have
reasonable fallback behavior.

This file serves as a regression gate: any configuration change that breaks
intended ordering or consistency will be caught here.
"""

from __future__ import annotations

import json
import logging

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _non_chitchat_types() -> set[str]:
    """Return the 4 retrieval-relevant query types (excludes chitchat and default)."""
    return {"factual", "summary", "analytical", "multi_hop"}


def _all_known_types() -> set[str]:
    """Return all query types that have explicit entries (excludes default)."""
    return {"factual", "summary", "analytical", "multi_hop", "chitchat"}


def _capture_metrics_logs(caplog, logger_name: str = "agent_metrics") -> list[dict]:
    """Extract parsed JSON payloads from the agent_metrics logger output."""
    records = [r for r in caplog.records if r.name == logger_name]
    return [json.loads(r.message) for r in records]


# ---------------------------------------------------------------------------
# Test: per-type retrieval config sanity
# ---------------------------------------------------------------------------


class TestRetrievalConfigPerType:
    """Each query type's retrieval config values must be in reasonable ranges."""

    @pytest.fixture
    def config(self):
        from app.agent.nodes.retrieval_node import RETRIEVAL_CONFIG

        return RETRIEVAL_CONFIG

    @pytest.mark.parametrize(
        "qtype, expected",
        [
            ("factual", {"rerank_top_k": 5, "k_per_query": 20, "fusion_top_n": 15}),
            ("analytical", {"rerank_top_k": 5, "k_per_query": 30, "fusion_top_n": 30}),
            ("multi_hop", {"rerank_top_k": 8, "k_per_query": 30, "fusion_top_n": 30}),
            ("summary", {"rerank_top_k": 10, "k_per_query": 40, "fusion_top_n": 40}),
            ("default", {"rerank_top_k": 5, "k_per_query": 30, "fusion_top_n": 30}),
        ],
    )
    def test_expected_values(self, config, qtype, expected):
        """Verify exact config values for each type (regression gate)."""
        assert qtype in config, f"{qtype} missing from RETRIEVAL_CONFIG"
        assert config[qtype] == expected, (
            f"{qtype}: expected {expected}, got {config[qtype]}"
        )

    def test_all_non_chitchat_types_have_rerank_top_k_ge_3(self, config):
        """No type should return fewer than 3 chunks — that risks missing answers."""
        for qtype in _non_chitchat_types():
            if qtype in config:
                assert config[qtype]["rerank_top_k"] >= 3, (
                    f"{qtype} rerank_top_k={config[qtype]['rerank_top_k']} < 3"
                )

    def test_all_types_have_k_per_query_le_50(self, config):
        """k_per_query should not exceed 50 to avoid excessive API calls."""
        for qtype in _non_chitchat_types():
            if qtype in config:
                assert config[qtype]["k_per_query"] <= 50, (
                    f"{qtype} k_per_query={config[qtype]['k_per_query']} > 50"
                )

    def test_fusion_top_n_le_k_per_query(self, config):
        """fusion_top_n must not exceed k_per_query (cannot fuse more than retrieved)."""
        for qtype in _non_chitchat_types():
            if qtype in config:
                assert config[qtype]["fusion_top_n"] <= config[qtype]["k_per_query"], (
                    f"{qtype}: fusion_top_n({config[qtype]['fusion_top_n']}) > "
                    f"k_per_query({config[qtype]['k_per_query']})"
                )

    def test_rerank_top_k_le_fusion_top_n(self, config):
        """rerank_top_k must not exceed fusion_top_n (cannot rerank more than fused)."""
        for qtype in _non_chitchat_types():
            if qtype in config:
                assert config[qtype]["rerank_top_k"] <= config[qtype]["fusion_top_n"], (
                    f"{qtype}: rerank_top_k({config[qtype]['rerank_top_k']}) > "
                    f"fusion_top_n({config[qtype]['fusion_top_n']})"
                )


# ---------------------------------------------------------------------------
# Test: retrieval intensity order
# ---------------------------------------------------------------------------


class TestRetrievalIntensityOrder:
    """Retrieval intensity should follow: factual < analytical <= multi_hop < summary."""

    def test_factual_is_lightest(self):
        """factual should have the smallest k_per_query and fusion_top_n."""
        from app.agent.nodes.retrieval_node import RETRIEVAL_CONFIG as C

        types = _non_chitchat_types()
        factual_k = C["factual"]["k_per_query"]
        factual_fusion = C["factual"]["fusion_top_n"]
        for t in types - {"factual"}:
            assert factual_k <= C[t]["k_per_query"], (
                f"factual k_per_query({factual_k}) > {t}({C[t]['k_per_query']})"
            )
            assert factual_fusion <= C[t]["fusion_top_n"], (
                f"factual fusion_top_n({factual_fusion}) > {t}({C[t]['fusion_top_n']})"
            )

    def test_summary_is_heaviest(self):
        """summary should have the largest k_per_query and fusion_top_n."""
        from app.agent.nodes.retrieval_node import RETRIEVAL_CONFIG as C

        summary_k = C["summary"]["k_per_query"]
        summary_fusion = C["summary"]["fusion_top_n"]
        for t in _non_chitchat_types() - {"summary"}:
            assert summary_k >= C[t]["k_per_query"], (
                f"summary k_per_query({summary_k}) < {t}({C[t]['k_per_query']})"
            )
            assert summary_fusion >= C[t]["fusion_top_n"], (
                f"summary fusion_top_n({summary_fusion}) < {t}({C[t]['fusion_top_n']})"
            )

    def test_multi_hop_ge_analytical_in_rerank(self):
        """multi_hop should return ≥ chunks than analytical for cross-doc connections."""
        from app.agent.nodes.retrieval_node import RETRIEVAL_CONFIG as C

        assert C["multi_hop"]["rerank_top_k"] >= C["analytical"]["rerank_top_k"]


# ---------------------------------------------------------------------------
# Test: thinking effort order
# ---------------------------------------------------------------------------

_EFFORT_ORDER = {None: 0, "high": 1, "max": 2}


def _effort_sort_key(effort):
    """Map effort levels (None, 'high', 'max') to sortable ints."""
    return _EFFORT_ORDER.get(effort, -1)


class TestThinkingEffortOrder:
    """Effort level order: None < high < max."""

    @pytest.fixture
    def effort_map(self):
        from app.agent.nodes.qa_node import _QUERY_TYPE_EFFORT

        return _QUERY_TYPE_EFFORT

    def test_chitchat_has_no_effort(self, effort_map):
        assert effort_map["chitchat"] is None

    def test_factual_uses_high(self, effort_map):
        """factual, summary, analytical all use 'high' effort."""
        assert effort_map["factual"] == "high"

    def test_summary_uses_high(self, effort_map):
        assert effort_map["summary"] == "high"

    def test_analytical_uses_high(self, effort_map):
        assert effort_map["analytical"] == "high"

    def test_multi_hop_uses_max(self, effort_map):
        assert effort_map["multi_hop"] == "max"

    def test_multi_hop_gte_all_others(self, effort_map):
        """multi_hop should be max — >= all other types."""
        for t in _all_known_types() - {"multi_hop"}:
            assert _effort_sort_key(effort_map["multi_hop"]) >= _effort_sort_key(effort_map[t]), (
                f"multi_hop({effort_map['multi_hop']}) should be >= {t}({effort_map[t]})"
            )


# ---------------------------------------------------------------------------
# Test: history window order
# ---------------------------------------------------------------------------


class TestHistoryWindowOrder:
    """History window order: factual < summary < analytical <= multi_hop."""

    @pytest.fixture
    def window_map(self):
        from app.agent.nodes.qa_node import _HISTORY_WINDOW

        return _HISTORY_WINDOW

    def test_factual_smallest(self, window_map):
        for t in _non_chitchat_types() - {"factual"}:
            assert window_map["factual"] < window_map[t], (
                f"factual({window_map['factual']}) should be < {t}({window_map[t]})"
            )

    def test_summary_between_factual_and_analytical(self, window_map):
        assert window_map["factual"] < window_map["summary"] < window_map["analytical"]

    def test_multi_hop_largest(self, window_map):
        """multi_hop needs the most history for cross-turn reasoning."""
        for t in _non_chitchat_types() - {"multi_hop"}:
            assert window_map["multi_hop"] > window_map[t], (
                f"multi_hop({window_map['multi_hop']}) should be > {t}({window_map[t]})"
            )


# ---------------------------------------------------------------------------
# Test: verification scope
# ---------------------------------------------------------------------------


class TestVerificationScope:
    """Only analytical and multi_hop queries trigger verification."""

    def test_only_analytical_and_multi_hop_have_thresholds(self):
        from app.agent.nodes.answer_verifier import _VERIFICATION_THRESHOLDS

        assert set(_VERIFICATION_THRESHOLDS.keys()) == {"analytical", "multi_hop"}, (
            f"Unexpected verification thresholds: {_VERIFICATION_THRESHOLDS.keys()}"
        )

    def test_analytical_threshold_looser_than_multi_hop(self):
        from app.agent.nodes.answer_verifier import _VERIFICATION_THRESHOLDS

        assert _VERIFICATION_THRESHOLDS["analytical"] < _VERIFICATION_THRESHOLDS["multi_hop"], (
            "analytical threshold should be more lenient (<) than multi_hop"
        )

    def test_analytical_threshold_is_0_6(self):
        from app.agent.nodes.answer_verifier import _VERIFICATION_THRESHOLDS

        assert _VERIFICATION_THRESHOLDS["analytical"] == 0.6

    def test_multi_hop_threshold_is_0_7(self):
        from app.agent.nodes.answer_verifier import _VERIFICATION_THRESHOLDS

        assert _VERIFICATION_THRESHOLDS["multi_hop"] == 0.7


# ---------------------------------------------------------------------------
# Test: default fallback
# ---------------------------------------------------------------------------


class TestDefaultFallback:
    """Default strategy must exist and use conservative values."""

    def test_retrieval_config_has_default(self):
        from app.agent.nodes.retrieval_node import RETRIEVAL_CONFIG as C

        assert "default" in C

    def test_retrieval_strategies_has_default(self):
        from app.agent.nodes.query_classifier import RETRIEVAL_STRATEGIES as S

        assert "default" in S

    def test_default_retrieval_is_conservative(self):
        """Default should use moderate values — not the extremes."""
        from app.agent.nodes.retrieval_node import RETRIEVAL_CONFIG as C

        default = C["default"]
        assert 20 <= default["k_per_query"] <= 40
        assert 20 <= default["fusion_top_n"] <= 40
        assert 3 <= default["rerank_top_k"] <= 10

    def test_default_strategy_is_safe(self):
        """Default strategy should not trigger HyDE or multi-query."""
        from app.agent.nodes.query_classifier import RETRIEVAL_STRATEGIES as S

        default = S["default"]
        assert default["use_hyde"] is False, "default should not enable HyDE"
        assert default["multi_query_count"] == 1, "default should use single query"


# ---------------------------------------------------------------------------
# Test: config consistency across modules
# ---------------------------------------------------------------------------


class TestConfigConsistency:
    """Config maps in different modules should agree on query type sets."""

    def test_retrieval_types_cover_strategy_types(self):
        """Every type in RETRIEVAL_STRATEGIES (except chitchat, default) must be in RETRIEVAL_CONFIG."""
        from app.agent.nodes.query_classifier import RETRIEVAL_STRATEGIES as S
        from app.agent.nodes.retrieval_node import RETRIEVAL_CONFIG as C

        for qtype in S:
            if qtype == "chitchat":
                # chitchat never reaches retrieval → not needed in RETRIEVAL_CONFIG
                continue
            assert qtype in C, f"RETRIEVAL_CONFIG missing type '{qtype}' (exists in RETRIEVAL_STRATEGIES)"

    def test_effort_covers_all_retrieval_types(self):
        """Every non-chitchat type in STRATEGIES should have an effort entry."""
        from app.agent.nodes.query_classifier import RETRIEVAL_STRATEGIES as S
        from app.agent.nodes.qa_node import _QUERY_TYPE_EFFORT

        for qtype in _non_chitchat_types():
            if qtype in S:
                assert qtype in _QUERY_TYPE_EFFORT, (
                    f"_QUERY_TYPE_EFFORT missing type '{qtype}'"
                )

    def test_history_window_covers_all_retrieval_types(self):
        """Every non-chitchat type should have a history window entry."""
        from app.agent.nodes.qa_node import _HISTORY_WINDOW

        for qtype in _non_chitchat_types():
            assert qtype in _HISTORY_WINDOW, (
                f"_HISTORY_WINDOW missing type '{qtype}'"
            )

    def test_state_docstring_lists_all_types(self):
        """The state.py docstring should cover all known types."""
        from app.agent.state import AgentState

        # The TypedDict annotation comment lists the types
        # This is a smoke test: we just validate the field exists
        assert "query_type" in AgentState.__annotations__


# ---------------------------------------------------------------------------
# Test: metrics tracker
# ---------------------------------------------------------------------------


class TestMetricsTracker:
    """MetricsTracker log methods produce valid JSON with correct event fields."""

    @pytest.fixture
    def tracker(self):
        from app.agent.metrics import get_metrics_tracker

        # Reset singleton for test isolation
        import app.agent.metrics as mod

        mod._tracker = None
        return get_metrics_tracker()

    def test_log_retrieval_emits_valid_json(self, tracker, caplog):
        """log_retrieval should emit a valid JSON line with event='retrieval'."""
        caplog.set_level(logging.INFO, logger="agent_metrics")
        tracker.log_retrieval(
            query_type="factual",
            rerank_scores=[0.92, 0.88, 0.76, 0.45, 0.30],
            rerank_top_k=5,
            queried_doc_count=15,
            search_strategy={"use_hyde": False, "multi_query_count": 1},
            latency_ms=342.5,
            kb_id="abc123",
        )
        payloads = _capture_metrics_logs(caplog)
        assert len(payloads) == 1
        p = payloads[0]
        assert p["event"] == "retrieval"
        assert p["query_type"] == "factual"
        assert p["rerank_top_k"] == 5
        assert p["queried_doc_count"] == 15
        assert p["fusion_utilization"] == pytest.approx(5 / 15, rel=1e-3)
        assert len(p["rerank_scores"]) == 5
        assert p["score_drop_k"] == 4  # drops from 0.76 to 0.45 (>30%)
        assert p["search_strategy"] == {"use_hyde": False, "multi_query_count": 1}
        assert p["latency_ms"] == 342.5
        assert p["kb_id"] == "abc123"

    def test_log_retrieval_no_score_drop_when_smooth(self, tracker, caplog):
        """When scores decline smoothly, score_drop_k should be None."""
        caplog.set_level(logging.INFO, logger="agent_metrics")
        tracker.log_retrieval(
            query_type="summary",
            rerank_scores=[0.90, 0.85, 0.81, 0.77, 0.73],
            rerank_top_k=10,
            queried_doc_count=40,
            search_strategy={"use_hyde": False, "multi_query_count": 2},
            latency_ms=500.0,
            kb_id="def456",
        )
        payloads = _capture_metrics_logs(caplog)
        assert payloads[0]["score_drop_k"] is None

    def test_log_retrieval_single_score(self, tracker, caplog):
        """Single document: score_drop_k should be None (need ≥2 to compute)."""
        caplog.set_level(logging.INFO, logger="agent_metrics")
        tracker.log_retrieval(
            query_type="factual",
            rerank_scores=[0.95],
            rerank_top_k=1,
            queried_doc_count=1,
            search_strategy={"use_hyde": False, "multi_query_count": 1},
            latency_ms=100.0,
            kb_id="",
        )
        payloads = _capture_metrics_logs(caplog)
        assert payloads[0]["score_drop_k"] is None

    def test_log_verification_emits_valid_json(self, tracker, caplog):
        """log_verification should emit valid JSON with event='verification'."""
        caplog.set_level(logging.INFO, logger="agent_metrics")
        tracker.log_verification(
            query_type="multi_hop",
            quality_score=0.72,
            verification_type="full",
            needs_refine=True,
            kb_id="abc123",
        )
        payloads = _capture_metrics_logs(caplog)
        assert len(payloads) == 1
        p = payloads[0]
        assert p["event"] == "verification"
        assert p["query_type"] == "multi_hop"
        assert p["quality_score"] == 0.72
        assert p["verification_type"] == "full"
        assert p["needs_refine"] is True

    def test_log_classification_emits_valid_json(self, tracker, caplog):
        """log_classification should emit valid JSON with event='classification'."""
        caplog.set_level(logging.INFO, logger="agent_metrics")
        tracker.log_classification(
            query_type="factual",
            needs_retrieval=True,
            reasoning="涉及特定术语",
        )
        payloads = _capture_metrics_logs(caplog)
        assert len(payloads) == 1
        p = payloads[0]
        assert p["event"] == "classification"
        assert p["query_type"] == "factual"
        assert p["needs_retrieval"] is True
        assert p["reasoning"] == "涉及特定术语"

    def test_log_classification_non_ascii_reasoning(self, tracker, caplog):
        """Chinese reasoning text should be preserved."""
        caplog.set_level(logging.INFO, logger="agent_metrics")
        tracker.log_classification(
            query_type="multi_hop",
            needs_retrieval=True,
            reasoning="需要跨文档对比SEEDER与RAGAS",
        )
        payloads = _capture_metrics_logs(caplog)
        assert "SEEDER" in payloads[0]["reasoning"]


# ---------------------------------------------------------------------------
# Test: score drop computation
# ---------------------------------------------------------------------------


class TestComputeScoreDropK:
    """Tests for _compute_score_drop_k helper."""

    def test_drop_in_middle(self):
        from app.agent.metrics import _compute_score_drop_k

        assert _compute_score_drop_k([0.9, 0.8, 0.5, 0.4, 0.3]) == 3
        # 0.8 → 0.5 is a 37.5% drop

    def test_drop_at_start(self):
        from app.agent.metrics import _compute_score_drop_k

        assert _compute_score_drop_k([0.9, 0.4, 0.3]) == 2
        # 0.9 → 0.4 is a 55.6% drop

    def test_no_drop(self):
        from app.agent.metrics import _compute_score_drop_k

        assert _compute_score_drop_k([0.9, 0.85, 0.81]) is None

    def test_empty_list(self):
        from app.agent.metrics import _compute_score_drop_k

        assert _compute_score_drop_k([]) is None

    def test_single_element(self):
        from app.agent.metrics import _compute_score_drop_k

        assert _compute_score_drop_k([0.9]) is None

    def test_custom_threshold(self):
        from app.agent.metrics import _compute_score_drop_k

        # 10% threshold: 0.9 → 0.8 is 11.1% > 10%
        assert _compute_score_drop_k([0.9, 0.8, 0.7], threshold=0.1) == 2

    def test_zero_score_ignored(self):
        from app.agent.metrics import _compute_score_drop_k

        # Previous score is 0, can't compute drop fraction
        assert _compute_score_drop_k([0.0, 0.5]) is None
