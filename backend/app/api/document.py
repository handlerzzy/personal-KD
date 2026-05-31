from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import KB_DIR, UPLOAD_DIR
from app.document.chunker import split_text
from app.document.embedder import embed_texts
from app.document.parser import parse_document
from app.models.document import Document
from app.retrieval import dense, sparse

router = APIRouter(prefix="/knowledge-bases/{kb_id}/documents", tags=["Documents"])

ALLOWED_TYPES = {"pdf": "pdf", "txt": "txt", "md": "md", "markdown": "md"}


def _kb_path(kb_id: str) -> Path:
    path = KB_DIR / kb_id
    if not path.exists():
        raise HTTPException(404, "知识库不存在")
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
    kb_path = _kb_path(kb_id)

    # Validate file type
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    file_type = ALLOWED_TYPES.get(ext)
    if not file_type:
        raise HTTPException(400, f"不支持的文件类型: .{ext}，仅支持 PDF/TXT/MD")

    # Save uploaded file
    upload_dir = UPLOAD_DIR / kb_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Create doc record
    doc = Document(
        kb_id=kb_id,
        filename=file.filename,
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
        # Cleanup on failure
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(500, f"文档处理失败: {str(e)}")

    # Save doc metadata
    _save_doc(doc)

    # Update KB doc count
    from app.models.kb import KnowledgeBase
    meta_file = kb_path / "meta.json"
    if meta_file.exists():
        with open(meta_file) as f:
            kb = KnowledgeBase(**json.load(f))
        kb.doc_count = len(_load_docs(kb_id))
        with open(meta_file, "w") as f:
            json.dump(kb.model_dump(), f, ensure_ascii=False, indent=2)

    return doc


@router.delete("/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    kb_path = _kb_path(kb_id)
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

    return {"ok": True}
