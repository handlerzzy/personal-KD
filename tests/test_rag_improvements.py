"""Test RAG improvements: chunking, retrieval, source display."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add backend to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


# ---------------------------------------------------------------------------
# Test 1: Chunking parameters
# ---------------------------------------------------------------------------


class TestChunkingParameters:
    """Verify chunker uses updated chunk_size and chunk_overlap."""

    def test_default_chunk_size(self):
        """Default chunk_size should be 1500 (was 800)."""
        import inspect
        from app.document.chunker import split_text

        sig = inspect.signature(split_text)
        default_chunk_size = sig.parameters["chunk_size"].default
        assert default_chunk_size == 1500, f"Expected 1500, got {default_chunk_size}"

    def test_default_chunk_overlap(self):
        """Default chunk_overlap should be 200 (was 150)."""
        import inspect
        from app.document.chunker import split_text

        sig = inspect.signature(split_text)
        default_overlap = sig.parameters["chunk_overlap"].default
        assert default_overlap == 200, f"Expected 200, got {default_overlap}"

    def test_chunks_are_larger(self):
        """Chunks should respect the new 1500-char limit."""
        from app.document.chunker import split_text

        # Generate a long paragraph (> 1500 chars) to test chunking
        long_paragraph = "这是一段很长的测试文本。" * 100  # ~900 chars
        text = f"""
# 第一章

{long_paragraph}

# 第二章

{long_paragraph}
"""
        chunks = split_text(text, kb_id="test_kb", doc_id="test_doc")

        # All chunks should be <= 1500 chars
        for chunk in chunks:
            assert len(chunk["text"]) <= 1500, f"Chunk too large: {len(chunk['text'])} chars"

        # Verify chunking happened (multiple chunks for long text)
        assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"


# ---------------------------------------------------------------------------
# Test 2: Retrieval parameters
# ---------------------------------------------------------------------------


class TestRetrievalParameters:
    """Verify retrieval node uses updated top_n."""

    def test_rerank_top_n(self):
        """Rerank should use top_n=10 (was 5)."""
        import inspect
        from app.agent.nodes.retrieval_node import retrieval_node

        source = inspect.getsource(retrieval_node)
        assert "top_n=10" in source, "Expected top_n=10 in retrieval_node"


# ---------------------------------------------------------------------------
# Test 3: Source building
# ---------------------------------------------------------------------------


class TestSourceBuilding:
    """Verify source building includes filename and heading."""

    def test_build_sources_includes_filename(self):
        """_build_sources should include filename field."""
        import inspect
        from app.agent.nodes.qa_node import _build_sources

        source = inspect.getsource(_build_sources)
        assert '"filename"' in source, "Expected filename field in _build_sources"

    def test_build_sources_includes_heading(self):
        """_build_sources should include heading field."""
        import inspect
        from app.agent.nodes.qa_node import _build_sources

        source = inspect.getsource(_build_sources)
        assert '"heading"' in source, "Expected heading field in _build_sources"

    def test_build_sources_from_docs_includes_filename(self):
        """_build_sources_from_docs should include filename field."""
        import inspect
        from app.api.chat import _build_sources_from_docs

        source = inspect.getsource(_build_sources_from_docs)
        assert '"filename"' in source, "Expected filename field in _build_sources_from_docs"

    def test_build_sources_from_docs_includes_heading(self):
        """_build_sources_from_docs should include heading field."""
        import inspect
        from app.api.chat import _build_sources_from_docs

        source = inspect.getsource(_build_sources_from_docs)
        assert '"heading"' in source, "Expected heading field in _build_sources_from_docs"


# ---------------------------------------------------------------------------
# Test 4: Citation removal
# ---------------------------------------------------------------------------


class TestCitationRemoval:
    """Verify citation references are stripped from answers."""

    def test_strip_citations(self):
        """_strip_internal_data should remove [1], [2], [10] etc."""
        from app.agent.nodes.qa_node import _strip_internal_data

        test_cases = [
            ("RAG评估包括[1][3]两个维度", "RAG评估包括两个维度"),
            ("根据文档[10]，答案是...", "根据文档，答案是..."),
            ("测试[1][2][3]引用", "测试引用"),
            ("无引用的正常文本", "无引用的正常文本"),
        ]

        for input_text, expected in test_cases:
            result = _strip_internal_data(input_text)
            assert result == expected, f"Input: {input_text!r}, Expected: {expected!r}, Got: {result!r}"

    def test_strip_citations_in_chat(self):
        """_strip_answer should remove citation references."""
        from app.api.chat import _strip_answer

        test_cases = [
            ("RAG评估包括[1][3]两个维度", "RAG评估包括两个维度"),
            ("根据文档[10]，答案是...", "根据文档，答案是..."),
        ]

        for input_text, expected in test_cases:
            result = _strip_answer(input_text)
            assert result == expected, f"Input: {input_text!r}, Expected: {expected!r}, Got: {result!r}"


# ---------------------------------------------------------------------------
# Test 5: System prompt
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """Verify system prompt discourages citation references."""

    def test_no_citation_instruction(self):
        """System prompt should not instruct LLM to use citation references."""
        from app.agent.nodes.qa_node import _build_system_prompt

        prompt = _build_system_prompt("test context")
        assert "标注来源编号" not in prompt, "System prompt should not instruct citation references"
        assert "不要在回答中使用 [1][2][3] 等引用编号" in prompt, "System prompt should prohibit citation references"


# ---------------------------------------------------------------------------
# Test 6: Frontend types
# ---------------------------------------------------------------------------


class TestFrontendTypes:
    """Verify frontend TypeScript types include new fields."""

    def test_source_type_has_filename(self):
        """Source type should include filename field."""
        types_file = Path(__file__).parent.parent / "frontend" / "src" / "types" / "index.ts"
        content = types_file.read_text(encoding="utf-8")
        assert "filename?: string" in content, "Source type should include filename"

    def test_source_type_has_heading(self):
        """Source type should include heading field."""
        types_file = Path(__file__).parent.parent / "frontend" / "src" / "types" / "index.ts"
        content = types_file.read_text(encoding="utf-8")
        assert "heading?: string" in content, "Source type should include heading"
