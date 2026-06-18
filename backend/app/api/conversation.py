from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.deps import get_user_conv, get_user_kb
from app.persistence.conv_repo import ConvRepository
from app.persistence.message_repo import MessageRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-bases/{kb_id}/conversations", tags=["Conversations"])


@router.get("")
async def list_conversations(
    kb: Annotated[dict, Depends(get_user_kb)],
):
    """List conversations for a knowledge base (must belong to current user)."""
    return await ConvRepository.list_by_kb(kb["id"])


class CreateConvRequest(BaseModel):
    title: str = "新对话"


@router.post("", status_code=201)
async def create_conversation(
    req: CreateConvRequest,
    kb: Annotated[dict, Depends(get_user_kb)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Create a new conversation (must belong to current user)."""
    conv = await ConvRepository.create(kb_id=kb["id"], title=req.title, user_id=current_user["id"])
    logger.info(
        "Conversation created: id=%s, kb_id=%s, user_id=%s",
        conv["id"],
        kb["id"],
        current_user["id"],
    )
    return conv


@router.put("/{conv_id}")
async def update_conversation(
    conv_id: str,
    req: CreateConvRequest,
    conv: Annotated[dict, Depends(get_user_conv)],
):
    """Update conversation (must belong to current user)."""
    await ConvRepository.update_title(conv_id, req.title)
    return await ConvRepository.get(conv_id)


@router.delete("/{conv_id}")
async def delete_conversation(
    conv_id: str,
    conv: Annotated[dict, Depends(get_user_conv)],
):
    """Delete conversation (must belong to current user)."""
    await ConvRepository.delete(conv_id)
    logger.info("Conversation deleted: id=%s, kb_id=%s", conv_id, conv["kb_id"])
    return {"ok": True}


@router.patch("/{conv_id}/pin")
async def toggle_pin(
    conv_id: str,
    conv: Annotated[dict, Depends(get_user_conv)],
):
    """Toggle pin status (must belong to current user)."""
    updated = await ConvRepository.toggle_pin(conv_id)
    return updated


@router.get("/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    conv: Annotated[dict, Depends(get_user_conv)],
):
    """Get messages (must belong to current user)."""
    return await MessageRepository.get_messages(conv_id)
