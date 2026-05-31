from __future__ import annotations

import os
import tempfile
from pathlib import Path


async def parse_document(file_path: str, file_type: str) -> str:
    """Parse document and extract text content."""
    if file_type == "pdf":
        return await _parse_pdf(file_path)
    elif file_type in ("txt", "md"):
        return _parse_text(file_path)
    raise ValueError(f"Unsupported file type: {file_type}")


def _parse_text(file_path: str) -> str:
    with open(file_path, encoding="utf-8", errors="replace") as f:
        return f.read()


async def _parse_pdf(file_path: str) -> str:
    """Parse PDF using MinerU (magic-pdf)."""
    try:
        from magic_pdf.pipe import UNIPipe
        from magic_pdf.pipe.OCRPipe import OCRPipe
        from magic_pdf.rw.AbsReaderWriter import ImageWriter
    except ImportError:
        raise ImportError(
            "MinerU not installed. Run: pip install magic-pdf[full]"
        )

    # MinerU supports two pipelines: UNIPipe (auto) and OCRPipe (OCR-based)
    # auto mode uses built-in model detection, falls back to OCR if needed
    # We use CPU mode to save GPU memory for reranker
    os.environ["MINERU_DEVICE"] = "cpu"
    os.environ["MAGIC_PDF_DEVICE"] = "cpu"

    with tempfile.TemporaryDirectory() as tmp_dir:
        # MinerU takes a PDF and outputs markdown to a specified directory
        # Using the command-line interface for simplicity
        import subprocess
        result = subprocess.run(
            ["magic-pdf", "-p", file_path, "-o", tmp_dir],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"MinerU failed: {result.stderr}")

        # Find the output markdown file
        output_dir = Path(tmp_dir)
        md_files = list(output_dir.rglob("*.md"))
        if md_files:
            return md_files[0].read_text(encoding="utf-8")

        # Fallback: try txt files
        txt_files = list(output_dir.rglob("*.txt"))
        if txt_files:
            return txt_files[0].read_text(encoding="utf-8")

        raise RuntimeError("MinerU produced no output files")
