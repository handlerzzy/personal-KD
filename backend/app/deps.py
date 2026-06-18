"""Common dependencies for API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from app.auth import get_current_user
from app.persistence.conv_repo import ConvRepository
from app.persistence.kb_repo import KbRepository


async def get_user_kb(
    kb_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Get knowledge base and verify ownership."""
    kb = await KbRepository.get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    if kb.get("user_id") != current_user["id"]:
        raise HTTPException(403, "无权访问此知识库")
    return kb


async def get_user_conv(
    kb_id: str,
    conv_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Get conversation and verify ownership."""
    conv = await ConvRepository.get(conv_id)
    if not conv or conv["kb_id"] != kb_id:
        raise HTTPException(404, "对话不存在")
    if conv.get("user_id") != current_user["id"]:
        raise HTTPException(403, "无权访问此对话")
    return conv
