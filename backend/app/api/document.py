from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import KB_DIR, UPLOAD_DIR
from app.document.chunker import split_text
from app.document.embedder import embed_texts
from app.document.parser import parse_document
from app.models.document import Document
from app.persistence.kb_repo import KbRepository
from app.retrieval import dense, sparse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-bases/{kb_id}/documents", tags=["Documents"])

ALLOWED_TYPES = {"pdf": "pdf", "txt": "txt", "md": "md", "markdown": "md"}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


def _validate_id(id_value: str, name: str = "ID") -> None:
    """Validate that an ID is a 12-char hex string (prevents path traversal)."""
    if not re.fullmatch(r"[0-9a-f]{12}", id_value):
        raise HTTPException(400, f"无效的{name}格式")


def _kb_path(kb_id: str) -> Path:
    _validate_id(kb_id, "知识库ID")
    path = KB_DIR / kb_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "documents").mkdir(exist_ok=True)
    return path


def _load_docs(kb_id: str) -> list[Document]:
    docs_dir = KB_DIR / kb_id / "documents"
    if not docs_dir.exists():
        return []
    docs = []
    for f in docs_dir.iterdir():
        if f.suffix == ".json":
            with open(f) as fh:
                docs.append(Document(**json.load(fh)))
    return sorted(docs, key=lambda d: d.created_at, reverse=True)


def _save_doc(doc: Document) -> None:
    docs_dir = KB_DIR / doc.kb_id / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    with open(docs_dir / f"{doc.id}.json", "w") as f:
        json.dump(doc.model_dump(), f, ensure_ascii=False, indent=2)


def _delete_doc_file(doc: Document) -> None:
    f = KB_DIR / doc.kb_id / "documents" / f"{doc.id}.json"
    if f.exists():
        f.unlink()


@router.get("")
async def list_documents(kb_id: str):
    _kb_path(kb_id)
    return _load_docs(kb_id)


@router.post("", status_code=201)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
):
    _kb_path(kb_id)

    # Validate file type
    original_name = file.filename or "unknown"
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    file_type = ALLOWED_TYPES.get(ext)
    if not file_type:
        raise HTTPException(400, f"不支持的文件类型: .{ext}，仅支持 PDF/TXT/MD")

    # Read with size limit
    content = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"文件过大，最大允许 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")

    # Sanitize filename (strip directory components to prevent path traversal)
    safe_name = Path(original_name).name

    # Save uploaded file
    upload_dir = UPLOAD_DIR / kb_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / safe_name
    with open(file_path, "wb") as f:
        f.write(content)

    # Create doc record
    doc = Document(
        kb_id=kb_id,
        filename=safe_name,
        file_type=file_type,
        file_size=len(content),
    )

    try:
        # Parse document
        text = await parse_document(str(file_path), file_type)
        # Chunk
        chunks = split_text(text, kb_id, doc.id)
        doc.chunk_count = len(chunks)

        if chunks:
            # Embed
            texts = [c["text"] for c in chunks]
            embeddings = await embed_texts(texts)
            # Index to Qdrant
            await dense.upsert_chunks(kb_id, chunks, embeddings)
            # Index to BM25
            sparse.add_documents(kb_id, texts)

    except Exception as e:
        logger.exception("文档处理失败: %s", e)
        # Cleanup on failure
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(500, f"文档处理失败: {str(e)}")

    # Save doc metadata (still using JSON for document metadata)
    _save_doc(doc)

    # Update KB doc count in SQLite
    await KbRepository.update_doc_count(kb_id, delta=1)

    return doc


@router.delete("/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    _validate_id(kb_id, "知识库ID")
    _validate_id(doc_id, "文档ID")
    _kb_path(kb_id)
    docs = _load_docs(kb_id)
    doc = next((d for d in docs if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "文档不存在")

    # Delete from Qdrant
    await dense.delete_document_chunks(kb_id, doc_id)

    # Delete from BM25 (not directly supported by bm25x, skip for now)

    # Delete file
    upload_path = UPLOAD_DIR / kb_id / doc.filename
    if upload_path.exists():
        upload_path.unlink()

    # Delete metadata
    _delete_doc_file(doc)

    # Update KB doc count in SQLite
    await KbRepository.update_doc_count(kb_id, delta=-1)

    return {"ok": True}
