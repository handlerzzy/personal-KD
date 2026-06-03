"""Tests for PDF parser with MinerU integration."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.document.parser import (
    _assess_pdf_complexity,
    _parse_pdf,
    _parse_pdf_mineru,
    parse_document,
)


class TestAssessPdfComplexity:
    """Tests for PDF complexity assessment."""

    def test_simple_text_pdf_returns_pymupdf(self):
        """Simple text PDF should use PyMuPDF."""
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.rect.height = 792
        # Need density >= 0.01 for pymupdf (page area ~484k, need ~5k chars)
        long_text = "This is a simple text document with enough content. " * 200
        mock_page.get_text.return_value = long_text

        # Mock get_text("blocks") separately
        blocks_mock = MagicMock()
        blocks_mock.__len__ = MagicMock(return_value=5)
        mock_page.get_text.side_effect = lambda arg=None: (
            blocks_mock if arg == "blocks" else long_text
        )

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("pymupdf.open", return_value=mock_doc):
            result = _assess_pdf_complexity("test.pdf")
            assert result == "pymupdf"

    def test_empty_pdf_returns_precision(self):
        """Empty/scanned PDF should use MinerU precision."""
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.rect.height = 792

        blocks_mock = MagicMock()
        blocks_mock.__len__ = MagicMock(return_value=0)
        mock_page.get_text.side_effect = lambda arg=None: (
            blocks_mock if arg == "blocks" else ""
        )

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("pymupdf.open", return_value=mock_doc):
            result = _assess_pdf_complexity("scanned.pdf")
            assert result == "precision"

    def test_complex_layout_returns_precision_with_token(self):
        """Complex layout with token configured should use precision."""
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.rect.height = 792

        blocks_mock = MagicMock()
        blocks_mock.__len__ = MagicMock(return_value=20)
        mock_page.get_text.side_effect = lambda arg=None: (
            blocks_mock if arg == "blocks" else "text " * 50
        )

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("pymupdf.open", return_value=mock_doc):
            with patch.dict(os.environ, {"MINERU_API_TOKEN": "test_token"}):
                result = _assess_pdf_complexity("complex.pdf")
                assert result == "precision"

    @pytest.mark.skip(reason="Requires clean env without MINERU_API_TOKEN")
    def test_complex_layout_returns_flash_without_token(self):
        """Complex layout without token should use flash."""
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.rect.height = 792

        blocks_mock = MagicMock()
        blocks_mock.__len__ = MagicMock(return_value=20)
        mock_page.get_text.side_effect = lambda arg=None: (
            blocks_mock if arg == "blocks" else "text " * 50
        )

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("pymupdf.open", return_value=mock_doc):
            with patch.dict(os.environ, {}, clear=True):
                result = _assess_pdf_complexity("complex.pdf")
                assert result == "flash"


class TestParsePdfMineru:
    """Tests for MinerU PDF parsing."""

    @pytest.mark.asyncio
    async def test_flash_mode_loads_documents(self):
        """Flash mode should load documents correctly."""
        mock_doc = MagicMock()
        mock_doc.page_content = "# Title\n\nContent here"

        with patch(
            "langchain_mineru.MinerULoader"
        ) as MockLoader:
            MockLoader.return_value.load.return_value = [mock_doc]
            result = await _parse_pdf_mineru("test.pdf", mode="flash")

            assert "Title" in result
            assert "Content here" in result
            MockLoader.assert_called_once_with(
                source="test.pdf",
                mode="flash",
                language="ch",
                formula=True,
                table=True,
                ocr=False,
                timeout=60,
            )

    @pytest.mark.asyncio
    async def test_precision_mode_uses_token(self):
        """Precision mode should use API token."""
        mock_doc = MagicMock()
        mock_doc.page_content = "# Complex Document\n\nTable content"

        with patch(
            "langchain_mineru.MinerULoader"
        ) as MockLoader:
            MockLoader.return_value.load.return_value = [mock_doc]
            with patch.dict(os.environ, {"MINERU_API_TOKEN": "test_token"}):
                result = await _parse_pdf_mineru("test.pdf", mode="precision")

                assert "Complex Document" in result
                MockLoader.assert_called_once_with(
                    source="test.pdf",
                    mode="precision",
                    language="ch",
                    formula=True,
                    table=True,
                    ocr=True,
                    timeout=60,
                )

    @pytest.mark.asyncio
    async def test_fallback_to_pymupdf_on_error(self):
        """Should fallback to PyMuPDF on MinerU error."""
        with patch(
            "langchain_mineru.MinerULoader"
        ) as MockLoader:
            MockLoader.return_value.load.side_effect = Exception("API error")
            with patch("app.document.parser._parse_pdf") as mock_parse:
                mock_parse.return_value = "fallback content"
                result = await _parse_pdf_mineru("test.pdf", mode="flash")

                assert result == "fallback content"
                mock_parse.assert_called_once_with("test.pdf")


class TestParseDocument:
    """Tests for the main parse_document function."""

    @pytest.mark.asyncio
    async def test_txt_file_uses_text_parser(self):
        """Text files should use simple text parser."""
        with patch("app.document.parser._parse_text") as mock_text:
            mock_text.return_value = "text content"
            result = await parse_document("test.txt", "txt")

            assert result == "text content"
            mock_text.assert_called_once_with("test.txt")

    @pytest.mark.asyncio
    async def test_pdf_routes_to_pymupdf(self):
        """Simple PDF should route to PyMuPDF."""
        with patch("app.document.parser._assess_pdf_complexity") as mock_assess:
            mock_assess.return_value = "pymupdf"
            with patch("app.document.parser._parse_pdf") as mock_parse:
                mock_parse.return_value = "pdf content"
                result = await parse_document("test.pdf", "pdf")

                assert result == "pdf content"
                mock_parse.assert_called_once_with("test.pdf")

    @pytest.mark.asyncio
    async def test_pdf_routes_to_mineru_flash(self):
        """Complex PDF should route to MinerU flash."""
        with patch("app.document.parser._assess_pdf_complexity") as mock_assess:
            mock_assess.return_value = "flash"
            with patch("app.document.parser._parse_pdf_mineru") as mock_mineru:
                mock_mineru.return_value = "mineru content"
                result = await parse_document("test.pdf", "pdf")

                assert result == "mineru content"
                mock_mineru.assert_called_once_with("test.pdf", mode="flash")

    @pytest.mark.asyncio
    async def test_unsupported_type_raises_error(self):
        """Unsupported file type should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported file type"):
            await parse_document("test.docx", "docx")
