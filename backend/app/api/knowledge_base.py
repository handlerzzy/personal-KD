from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import KB_DIR
from app.persistence.kb_repo import KbRepository
from app.retrieval import dense, sparse

router = APIRouter(prefix="/knowledge-bases", tags=["Knowledge Bases"])


@router.get("")
async def list_knowledge_bases():
    return await KbRepository.list_all()


class CreateKBRequest(BaseModel):
    name: str
    description: str = ""


@router.post("", status_code=201)
async def create_knowledge_base(req: CreateKBRequest):
    kb = await KbRepository.create(name=req.name, description=req.description)
    # Create file-based directories for documents
    kb_dir = KB_DIR / kb["id"]
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "documents").mkdir(exist_ok=True)
    # Create Qdrant collection and BM25 index
    await dense.create_collection(kb["id"])
    sparse.create_index(kb["id"])
    return kb


@router.put("/{kb_id}")
async def update_knowledge_base(kb_id: str, req: CreateKBRequest):
    kb = await KbRepository.get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    await KbRepository.update_name(kb_id, req.name, req.description)
    return await KbRepository.get(kb_id)


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    kb = await KbRepository.get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    await dense.delete_collection(kb_id)
    sparse.delete_index(kb_id)
    # Delete KB (cascades to conversations and messages in SQLite)
    await KbRepository.delete(kb_id)
    # Clean up file-based storage (documents, BM25 index)
    kb_dir = KB_DIR / kb_id
    if kb_dir.exists():
        shutil.rmtree(str(kb_dir))
    return {"ok": True}
