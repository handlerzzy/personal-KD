from __future__ import annotations

import logging
import shutil
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.config import KB_DIR
from app.deps import get_user_kb
from app.persistence.kb_repo import KbRepository
from app.retrieval import dense, sparse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-bases", tags=["Knowledge Bases"])


@router.get("")
async def list_knowledge_bases(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """List knowledge bases for current user."""
    return await KbRepository.list_by_user(current_user["id"])


class CreateKBRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


@router.post("", status_code=201)
async def create_knowledge_base(
    req: CreateKBRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Create a new knowledge base for current user."""
    kb = await KbRepository.create(
        name=req.name,
        description=req.description,
        user_id=current_user["id"],
    )
    # Create file-based directories for documents
    kb_dir = KB_DIR / kb["id"]
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "documents").mkdir(exist_ok=True)
    # Create Qdrant collection and BM25 index
    await dense.create_collection(kb["id"])
    sparse.create_index(kb["id"])
    logger.info(
        "Knowledge base created: id=%s, name=%s, user_id=%s",
        kb["id"],
        req.name,
        current_user["id"],
    )
    return kb


@router.put("/{kb_id}")
async def update_knowledge_base(
    req: CreateKBRequest,
    kb: Annotated[dict, Depends(get_user_kb)],
):
    """Update knowledge base (must belong to current user)."""
    await KbRepository.update_name(kb["id"], req.name, req.description)
    return await KbRepository.get(kb["id"])


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb: Annotated[dict, Depends(get_user_kb)],
):
    """Delete knowledge base (must belong to current user)."""
    kb_id = kb["id"]
    logger.info("Deleting knowledge base: id=%s, name=%s", kb_id, kb["name"])
    await dense.delete_collection(kb_id)
    sparse.delete_index(kb_id)
    # Delete KB (cascades to conversations and messages in SQLite)
    await KbRepository.delete(kb_id)
    # Clean up file-based storage (documents, BM25 index)
    kb_dir = KB_DIR / kb_id
    if kb_dir.exists():
        shutil.rmtree(str(kb_dir))
        logger.info("KB files removed: %s", kb_dir)
    return {"ok": True}
