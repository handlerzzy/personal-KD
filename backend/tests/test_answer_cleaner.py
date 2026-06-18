"""Tests for answer_cleaner.strip_answer — strips internal pipeline metadata from LLM output."""

from __future__ import annotations

from app.answer_cleaner import strip_answer


class TestStripAnswerBasic:
    """Basic behavior: pass-through for clean text."""

    def test_should_return_normal_text_unchanged(self):
        """Normal content without any metadata should pass through."""
        text = "RAG是一种结合检索与生成的技术，用于提升大模型的回答质量。"
        assert strip_answer(text) == text

    def test_should_return_empty_string_for_empty_input(self):
        """Empty string input should return empty string."""
        assert strip_answer("") == ""

    def test_should_return_none_for_none_input(self):
        """None input should return None (falsy guard)."""
        assert strip_answer(None) is None

    def test_should_preserve_multi_paragraph_content(self):
        """Multi-paragraph legitimate content should be preserved."""
        text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
        assert strip_answer(text) == text


class TestStripJsonMetadata:
    """Remove leading JSON objects containing query_type."""

    def test_should_remove_leading_json_with_query_type(self):
        text = '{"query_type": "factual", "needs_retrieval": true}\n这是实际回答。'
        result = strip_answer(text)
        assert "query_type" not in result
        assert "这是实际回答" in result

    def test_should_remove_json_with_whitespace_prefix(self):
        text = '  {"query_type": "analytical"}  \n回答内容。'
        result = strip_answer(text)
        assert "query_type" not in result
        assert "回答内容" in result

    def test_should_not_remove_json_without_query_type(self):
        """JSON without query_type key should be preserved."""
        text = '{"name": "test", "value": 42}\n回答内容。'
        result = strip_answer(text)
        assert '"name"' in result
        assert "回答内容" in result


class TestStripDocumentGrades:
    """Remove document grade lines like '文档1: relevant'."""

    def test_should_remove_single_grade_line(self):
        text = "回答内容。\n文档1: relevant"
        result = strip_answer(text)
        assert "relevant" not in result
        assert "回答内容" in result

    def test_should_remove_multiple_grade_lines(self):
        text = "回答内容。\n文档1: relevant 文档2: irrelevant 文档3: relevant"
        result = strip_answer(text)
        assert "irrelevant" not in result
        assert "回答内容" in result


class TestStripVerificationScores:
    """Remove verification score JSON blocks."""

    def test_should_remove_faithfulness_score_block(self):
        text = '回答内容。\n{"faithfulness_score": 0.85, "completeness_score": 0.7}'
        result = strip_answer(text)
        assert "faithfulness_score" not in result
        assert "回答内容" in result


class TestStripSuggestionFragments:
    """Remove suggestion fragments."""

    def test_should_remove_suggestion_with_english_colon(self):
        text = '回答内容。"suggestion": "请参考文档2"'
        result = strip_answer(text)
        assert "suggestion" not in result
        assert "回答内容" in result

    def test_should_remove_suggestion_with_chinese_colon(self):
        text = '回答内容。"suggestion"："请参考文档2"'
        result = strip_answer(text)
        assert "suggestion" not in result
        assert "回答内容" in result


class TestStripCitationReferences:
    """Remove citation references like [1], [2], [10]."""

    def test_should_remove_citation_at_end_of_sentence(self):
        text = "RAG是一种技术[1]。"
        result = strip_answer(text)
        assert "[1]" not in result
        assert "RAG是一种技术" in result

    def test_should_remove_citation_before_punctuation(self):
        text = "RAG是一种技术[1]，用于提升质量[2]。"
        result = strip_answer(text)
        assert "[1]" not in result
        assert "[2]" not in result

    def test_should_remove_consecutive_citations_after_bracket(self):
        """Citations preceded by ] are removed; first one preceded by Chinese is preserved."""
        text = "相关内容[1][2][3]已被验证。"
        result = strip_answer(text)
        # [1] is preceded by Chinese text — preserved by design
        assert "[1]" in result
        # [2] and [3] are preceded by ] — removed
        assert "[2]" not in result
        assert "[3]" not in result
        assert "相关内容" in result

    def test_should_remove_citation_at_line_end(self):
        text = "第一行引用[10]\n第二行内容。"
        result = strip_answer(text)
        assert "[10]" not in result
        assert "第一行引用" in result


class TestStripFallbackFragments:
    """Remove fallback fragments."""

    def test_should_remove_fallback_fragment_with_ascii_period(self):
        """Fallback regex requires ASCII period after '无法回答'."""
        text = "根据现有文档无法回答. 文档仅识别了部分内容。"
        result = strip_answer(text)
        assert "文档仅识别" not in result

    def test_should_not_remove_fallback_without_ascii_period(self):
        """Chinese period does not trigger the fallback regex (documented behavior)."""
        text = "根据现有文档无法回答。文档仅识别了部分内容。"
        result = strip_answer(text)
        # Chinese period does not match \. pattern — text preserved
        assert "文档仅识别" in result


class TestStripWhitespace:
    """Clean up excessive whitespace."""

    def test_should_collapse_excessive_newlines(self):
        text = "内容1。\n\n\n\n\n内容2。"
        result = strip_answer(text)
        assert "\n\n\n" not in result
        assert "内容1" in result
        assert "内容2" in result

    def test_should_strip_leading_trailing_whitespace(self):
        text = "  \n  回答内容。  \n  "
        result = strip_answer(text)
        assert result == "回答内容。"


class TestStripCombined:
    """Test combinations of multiple artifacts in one text."""

    def test_should_clean_complex_mixed_output(self):
        """Simulate a realistic messy LLM output."""
        text = (
            '{"query_type": "analytical", "needs_retrieval": true}\n'
            "RAG技术的优势包括[1]：\n"
            "1. 提升回答准确性[2]\n"
            "2. 减少幻觉[3]\n"
            "文档1: relevant 文档2: relevant\n"
            '{"faithfulness_score": 0.9}\n'
        )
        result = strip_answer(text)
        assert "query_type" not in result
        assert "[1]" not in result
        assert "[2]" not in result
        assert "[3]" not in result
        assert "relevant" not in result
        assert "faithfulness_score" not in result
        assert "RAG技术的优势包括" in result
        assert "提升回答准确性" in result
        assert "减少幻觉" in result
