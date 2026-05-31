from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.graph import stream_chat
from app.api.conversation import (
    _load_convs,
    _load_messages,
    _save_conv,
    _save_messages,
)
from app.config import KB_DIR
from app.models.conversation import Message

router = APIRouter(
    prefix="/knowledge-bases/{kb_id}/conversations/{conv_id}",
    tags=["Chat"],
)


class ChatRequest(BaseModel):
    query: str


@router.post("/chat")
async def chat(kb_id: str, conv_id: str, req: ChatRequest):
    # Verify KB and conversation exist
    if not (KB_DIR / kb_id).exists():
        raise HTTPException(404, "知识库不存在")
    convs = _load_convs(kb_id)
    conv = next((c for c in convs if c.id == conv_id), None)
    if not conv:
        raise HTTPException(404, "对话不存在")

    query = req.query.strip()
    if not query:
        raise HTTPException(400, "问题不能为空")

    # Load message history for context
    history_msgs = _load_messages(kb_id, conv_id)

    # Save user message immediately
    user_msg = Message(
        conversation_id=conv_id,
        role="user",
        content=query,
    )
    history_msgs.append(user_msg)
    _save_messages(kb_id, conv_id, history_msgs)

    async def event_generator():
        full_reasoning = ""
        full_answer = ""

        async for event in stream_chat(query, kb_id, conv_id, history=None):
            event_type = event["type"]
            event_data = event["data"]

            if event_type == "reasoning":
                data = json.loads(event_data)
                full_reasoning += data["token"]
                yield f"event: reasoning\ndata: {event_data}\n\n"

            elif event_type == "answer":
                data = json.loads(event_data)
                full_answer += data["token"]
                yield f"event: answer\ndata: {event_data}\n\n"

            elif event_type == "sources":
                yield f"event: sources\ndata: {event_data}\n\n"

            elif event_type == "done":
                # Save assistant message with full content
                assistant_msg = Message(
                    conversation_id=conv_id,
                    role="assistant",
                    content=full_answer,
                    reasoning_content=full_reasoning,
                )
                all_msgs = _load_messages(kb_id, conv_id)
                all_msgs.append(assistant_msg)
                _save_messages(kb_id, conv_id, all_msgs)

                # Update conversation
                convs = _load_convs(kb_id)
                conv = next((c for c in convs if c.id == conv_id), None)
                if conv:
                    conv.message_count = len(all_msgs)
                    from datetime import datetime
                    conv.updated_at = datetime.utcnow().isoformat()
                    _save_conv(conv)

                yield f"event: done\ndata: {event_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
