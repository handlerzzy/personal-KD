from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.persistence.conv_repo import ConvRepository
from app.persistence.kb_repo import KbRepository
from app.persistence.message_repo import MessageRepository

router = APIRouter(prefix="/knowledge-bases/{kb_id}/conversations", tags=["Conversations"])


@router.get("")
async def list_conversations(kb_id: str):
    kb = await KbRepository.get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    return await ConvRepository.list_by_kb(kb_id)


class CreateConvRequest(BaseModel):
    title: str = "新对话"


@router.post("", status_code=201)
async def create_conversation(kb_id: str, req: CreateConvRequest):
    kb = await KbRepository.get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    conv = await ConvRepository.create(kb_id=kb_id, title=req.title)
    return conv


@router.put("/{conv_id}")
async def update_conversation(kb_id: str, conv_id: str, req: CreateConvRequest):
    conv = await ConvRepository.get(conv_id)
    if not conv or conv["kb_id"] != kb_id:
        raise HTTPException(404, "对话不存在")
    await ConvRepository.update_title(conv_id, req.title)
    return await ConvRepository.get(conv_id)


@router.delete("/{conv_id}")
async def delete_conversation(kb_id: str, conv_id: str):
    conv = await ConvRepository.get(conv_id)
    if not conv or conv["kb_id"] != kb_id:
        raise HTTPException(404, "对话不存在")
    await ConvRepository.delete(conv_id)
    return {"ok": True}


@router.get("/{conv_id}/messages")
async def get_messages(kb_id: str, conv_id: str):
    conv = await ConvRepository.get(conv_id)
    if not conv or conv["kb_id"] != kb_id:
        raise HTTPException(404, "对话不存在")
    return await MessageRepository.get_messages(conv_id)
