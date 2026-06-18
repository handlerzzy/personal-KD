from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


async def parse_document(file_path: str, file_type: str) -> str:
    """Parse document and extract text content.

    For PDFs, automatically selects the best parser:
    - PyMuPDF: simple text PDFs (fast, no dependencies)
    - MinerU flash: moderate complexity (free API)
    - MinerU precision: complex PDFs with tables/formulas/scans (requires token)
    """
    if file_type == "pdf":
        parser_type = _assess_pdf_complexity(file_path)

        if parser_type == "pymupdf":
            return await _parse_pdf(file_path)
        elif parser_type == "flash":
            return await _parse_pdf_mineru(file_path, mode="flash")
        else:
            return await _parse_pdf_mineru(file_path, mode="precision")
    elif file_type in ("txt", "md"):
        return _parse_text(file_path)
    raise ValueError(f"Unsupported file type: {file_type}")


def _parse_text(file_path: str) -> str:
    with open(file_path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _assess_pdf_complexity(file_path: str) -> str:
    """Assess PDF complexity and return best parser type.

    Returns:
        'pymupdf' for simple text PDFs
        'flash' for moderate complexity (tables, layout)
        'precision' for complex PDFs (scans, formulas, dense tables)
    """
    try:
        import pymupdf
    except ImportError:
        logger.warning("PyMuPDF not installed, falling back to MinerU flash")
        return "flash"

    doc = pymupdf.open(file_path)
    try:
        total_pages = len(doc)

        # Sample first 3 pages for analysis
        sample_pages = min(3, total_pages)
        text_densities = []
        has_complex_layout = False

        for i in range(sample_pages):
            page = doc[i]
            rect = page.rect
            page_area = rect.width * rect.height

            # Get text content
            text = page.get_text()
            text_length = len(text.strip())
            text_density = text_length / page_area if page_area > 0 else 0
            text_densities.append(text_density)

            # Detect complex layout (many text blocks = tables/columns)
            blocks = page.get_text("blocks")
            if len(blocks) > 15:  # Heuristic for complex layout
                has_complex_layout = True

        avg_density = sum(text_densities) / len(text_densities) if text_densities else 0
        empty_pages = sum(1 for d in text_densities if d < 0.001)

        # Routing logic
        if empty_pages == sample_pages:
            # All sampled pages are empty = scanned PDF
            return "precision"
        elif avg_density >= 0.01 and not has_complex_layout:
            # Good text density, simple layout = use PyMuPDF
            return "pymupdf"
        elif has_complex_layout or avg_density < 0.01:
            # Complex layout or low text density = need MinerU
            # Check if precision mode is available (token configured)
            if os.getenv("MINERU_API_TOKEN"):
                return "precision"
            else:
                return "flash"
        else:
            return "pymupdf"

    except Exception as e:
        logger.warning("PDF 分析失败: %s, 回退到 MinerU flash", e)
        return "flash"
    finally:
        doc.close()


async def _parse_pdf(file_path: str) -> str:
    """Parse PDF using PyMuPDF."""
    try:
        import pymupdf
    except ImportError:
        raise ImportError("PyMuPDF not installed. Run: pip install pymupdf")

    doc = pymupdf.open(file_path)
    try:
        pages = []
        for page in doc:
            pages.append(page.get_text())
    finally:
        doc.close()

    text = "\n\n".join(pages)
    if not text.strip():
        raise RuntimeError("PDF 未提取到文本内容，可能是扫描件，需用 OCR 处理")
    return text


async def _parse_pdf_mineru(file_path: str, mode: str = "flash") -> str:
    """Parse PDF using MinerU via langchain-mineru.

    Args:
        file_path: Path to PDF file
        mode: 'flash' (free, no token) or 'precision' (requires MINERU_API_TOKEN)
    """
    try:
        from langchain_mineru import MinerULoader
    except ImportError:
        logger.warning("langchain-mineru 未安装，降级到 PyMuPDF")
        return await _parse_pdf(file_path)

    token = os.getenv("MINERU_API_TOKEN") if mode == "precision" else None

    if mode == "precision" and not token:
        logger.warning("MINERU_API_TOKEN 未配置，降级到 flash 模式")
        mode = "flash"

    try:
        loader = MinerULoader(
            source=file_path,
            mode=mode,
            language="ch",
            formula=True,
            table=True,
            ocr=(mode == "precision"),
            timeout=60,
            token=token,
        )

        docs = loader.load()
        text = "\n\n".join([doc.page_content for doc in docs])

        if not text.strip():
            raise RuntimeError("MinerU 未提取到文本内容")

        return text

    except Exception as e:
        logger.error("MinerU %s 解析失败: %s", mode, e)
        # Fallback to PyMuPDF
        logger.info("降级到 PyMuPDF 解析")
        return await _parse_pdf(file_path)
