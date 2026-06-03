from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.graph import stream_chat
from app.persistence.conv_repo import ConvRepository
from app.persistence.kb_repo import KbRepository
from app.persistence.message_repo import MessageRepository

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/knowledge-bases/{kb_id}/conversations/{conv_id}",
    tags=["Chat"],
)


class ChatRequest(BaseModel):
    query: str


def _build_sources_from_docs(docs: list[dict]) -> list[dict]:
    """Format retrieved docs into the SSE sources payload."""
    return [
        {
            "chunk_id": d.get("chunk_id", ""),
            "text": d.get("text", "")[:200],
            "score": round(d.get("score", 0.0), 4),
            "doc_id": d.get("doc_id", ""),
        }
        for d in docs
    ]


@router.post("/chat")
async def chat(kb_id: str, conv_id: str, req: ChatRequest):
    # Verify KB exists
    kb = await KbRepository.get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")

    # Verify conversation exists
    conv = await ConvRepository.get(conv_id)
    if not conv or conv["kb_id"] != kb_id:
        raise HTTPException(404, "对话不存在")

    query = req.query.strip()
    if not query:
        raise HTTPException(400, "问题不能为空")

    # Save user message immediately
    await MessageRepository.add_message(
        conversation_id=conv_id,
        role="user",
        content=query,
    )

    # Load history after saving user message (single query, includes the new message)
    history_msgs = await MessageRepository.get_messages(conv_id)

    async def event_generator():
        full_reasoning = ""
        full_answer = ""
        sources_emitted = False

        try:
            async for mode, data in stream_chat(query, kb_id, conv_id, history=history_msgs):
                if mode == "updates":
                    # Intercept retrieve node completion for sources
                    update_dict: dict = data
                    if "retrieve" in update_dict and not sources_emitted:
                        docs = update_dict["retrieve"].get("retrieved_docs", [])
                        sources = _build_sources_from_docs(docs)
                        yield f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"
                        sources_emitted = True

                elif mode == "messages":
                    # Token-level LLM output: (AIMessageChunk, metadata)
                    chunk, _metadata = data

                    # reasoning_content from additional_kwargs (Tier 1)
                    reasoning_token = chunk.additional_kwargs.get("reasoning_content", "")
                    # Fallback (Tier 2): Responses API key
                    if not reasoning_token:
                        reasoning_token = chunk.additional_kwargs.get("reasoning", "")
                    if reasoning_token:
                        full_reasoning += reasoning_token
                        yield (
                            f"event: reasoning\n"
                            f"data: {json.dumps({'token': reasoning_token})}\n\n"
                        )

                    # Main content token
                    content_token = chunk.content
                    if content_token:
                        full_answer += content_token
                        yield (
                            f"event: answer\n"
                            f"data: {json.dumps({'token': content_token})}\n\n"
                        )

            # Stream completed successfully — save assistant message
            await MessageRepository.add_message(
                conversation_id=conv_id,
                role="assistant",
                content=full_answer,
                reasoning_content=full_reasoning,
            )
            yield (
                f"event: done\n"
                f"data: {json.dumps({'reasoning': full_reasoning, 'answer': full_answer})}\n\n"
            )

        except Exception:
            logger.exception("Chat stream 失败: kb_id=%s, conv_id=%s", kb_id, conv_id)
            yield f"event: error\ndata: {json.dumps({'message': '对话处理失败'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
