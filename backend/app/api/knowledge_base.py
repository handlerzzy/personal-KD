from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import KB_DIR
from app.models.kb import KnowledgeBase
from app.retrieval import dense, sparse

router = APIRouter(prefix="/knowledge-bases", tags=["Knowledge Bases"])


def _load_all() -> list[KnowledgeBase]:
    if not KB_DIR.exists():
        return []
    kbs = []
    for folder in KB_DIR.iterdir():
        if folder.is_dir():
            meta_file = folder / "meta.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    kbs.append(KnowledgeBase(**json.load(f)))
    return kbs


def _save(kb: KnowledgeBase) -> None:
    kb_dir = KB_DIR / kb.id
    kb_dir.mkdir(parents=True, exist_ok=True)
    with open(kb_dir / "meta.json", "w") as f:
        json.dump(kb.model_dump(), f, ensure_ascii=False, indent=2)
    # Ensure subdirs
    (kb_dir / "documents").mkdir(exist_ok=True)
    (kb_dir / "conversations").mkdir(exist_ok=True)


def _load_kb(kb_id: str) -> KnowledgeBase:
    meta_file = KB_DIR / kb_id / "meta.json"
    if not meta_file.exists():
        raise HTTPException(404, "知识库不存在")
    with open(meta_file) as f:
        return KnowledgeBase(**json.load(f))


@router.get("")
async def list_knowledge_bases():
    return _load_all()


class CreateKBRequest(BaseModel):
    name: str
    description: str = ""


@router.post("", status_code=201)
async def create_knowledge_base(req: CreateKBRequest):
    kb = KnowledgeBase(name=req.name, description=req.description)
    _save(kb)
    # Create Qdrant collection and BM25 index
    await dense.create_collection(kb.id)
    sparse.create_index(kb.id)
    return kb


@router.put("/{kb_id}")
async def update_knowledge_base(kb_id: str, req: CreateKBRequest):
    kb = _load_kb(kb_id)
    kb.name = req.name
    kb.description = req.description
    _save(kb)
    return kb


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    _load_kb(kb_id)  # verify exists
    await dense.delete_collection(kb_id)
    sparse.delete_index(kb_id)
    shutil.rmtree(str(KB_DIR / kb_id))
    return {"ok": True}
