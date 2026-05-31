from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import KB_DIR
from app.models.conversation import Conversation, Message

router = APIRouter(prefix="/knowledge-bases/{kb_id}/conversations", tags=["Conversations"])


def _conv_dir(kb_id: str) -> str:
    path = KB_DIR / kb_id / "conversations"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _load_convs(kb_id: str) -> list[Conversation]:
    path = KB_DIR / kb_id / "conversations"
    if not path.exists():
        return []
    convs = []
    for f in path.iterdir():
        if f.is_dir():
            meta = f / "meta.json"
            if meta.exists():
                with open(meta) as fh:
                    convs.append(Conversation(**json.load(fh)))
    return sorted(convs, key=lambda c: c.updated_at, reverse=True)


def _save_conv(conv: Conversation) -> None:
    path = KB_DIR / conv.kb_id / "conversations" / conv.id
    path.mkdir(parents=True, exist_ok=True)
    with open(path / "meta.json", "w") as f:
        json.dump(conv.model_dump(), f, ensure_ascii=False, indent=2)


def _load_messages(kb_id: str, conv_id: str) -> list[Message]:
    msg_file = KB_DIR / kb_id / "conversations" / conv_id / "messages.json"
    if not msg_file.exists():
        return []
    with open(msg_file) as f:
        data = json.load(f)
    return [Message(**m) for m in data]


def _save_messages(kb_id: str, conv_id: str, messages: list[Message]) -> None:
    msg_file = KB_DIR / kb_id / "conversations" / conv_id / "messages.json"
    with open(msg_file, "w") as f:
        json.dump([m.model_dump() for m in messages], f, ensure_ascii=False, indent=2)


@router.get("")
async def list_conversations(kb_id: str):
    if not (KB_DIR / kb_id).exists():
        raise HTTPException(404, "知识库不存在")
    return _load_convs(kb_id)


class CreateConvRequest(BaseModel):
    title: str = "新对话"


@router.post("", status_code=201)
async def create_conversation(kb_id: str, req: CreateConvRequest):
    if not (KB_DIR / kb_id).exists():
        raise HTTPException(404, "知识库不存在")
    conv = Conversation(kb_id=kb_id, title=req.title)
    _save_conv(conv)
    # Update conv count in KB meta
    meta_file = KB_DIR / kb_id / "meta.json"
    if meta_file.exists():
        with open(meta_file) as f:
            from app.models.kb import KnowledgeBase
            kb = KnowledgeBase(**json.load(f))
        kb.conv_count = len(_load_convs(kb_id))
        with open(meta_file, "w") as f:
            json.dump(kb.model_dump(), f, ensure_ascii=False, indent=2)
    return conv


@router.put("/{conv_id}")
async def update_conversation(kb_id: str, conv_id: str, req: CreateConvRequest):
    convs = _load_convs(kb_id)
    conv = next((c for c in convs if c.id == conv_id), None)
    if not conv:
        raise HTTPException(404, "对话不存在")
    conv.title = req.title
    _save_conv(conv)
    return conv


@router.delete("/{conv_id}")
async def delete_conversation(kb_id: str, conv_id: str):
    path = KB_DIR / kb_id / "conversations" / conv_id
    if not path.exists():
        raise HTTPException(404, "对话不存在")
    import shutil
    shutil.rmtree(str(path))
    return {"ok": True}


@router.get("/{conv_id}/messages")
async def get_messages(kb_id: str, conv_id: str):
    path = KB_DIR / kb_id / "conversations" / conv_id
    if not path.exists():
        raise HTTPException(404, "对话不存在")
    return _load_messages(kb_id, conv_id)
