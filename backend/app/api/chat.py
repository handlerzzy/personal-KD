from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.agent.graph import stream_chat
from app.answer_cleaner import strip_answer
from app.auth import get_current_user
from app.config import settings
from app.deps import get_user_conv, get_user_kb
from app.persistence.conv_repo import ConvRepository
from app.persistence.message_repo import MessageRepository
from app.utils.sources import build_sources

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/knowledge-bases/{kb_id}/conversations/{conv_id}",
    tags=["Chat"],
)


class ChatRequest(BaseModel):
    query: str


async def _generate_title_async(
    conv_id: str,
    query: str,
    answer: str,
    queue: asyncio.Queue,
) -> None:
    """Generate conversation title asynchronously.

    Sends title_update event via queue when done.
    This function runs in background without blocking the main SSE stream.
    """
    try:
        # Use a separate LLM instance WITHOUT thinking mode for title generation
        # mimo-v2.5 with thinking enabled returns empty content, only reasoning_tokens
        title_llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_api_base,
            temperature=0.3,
            max_tokens=30,
            max_retries=1,
            # Disable thinking mode explicitly
            extra_body={"thinking": {"type": "disabled"}},
        )

        title_prompt = (
            "请用10字以内总结这段对话的核心内容，直接输出标题，不要加任何修饰：\n"
            f"用户：{query}\n助手：{answer[:200]}"
        )
        logger.debug("Generating title: conv_id=%s", conv_id)
        title_response = await title_llm.ainvoke(title_prompt)
        new_title = (
            title_response.content.strip().strip('"').strip("'").strip("\n")
            if title_response.content
            else ""
        )
        logger.info("Title generated: conv_id=%s, title=%s", conv_id, new_title)
        if new_title and len(new_title) <= 30:
            await ConvRepository.update_title(conv_id, new_title)
            # Send title_update event via queue
            await queue.put(("title_update", {"title": new_title}))
    except Exception:
        logger.exception("生成对话标题失败: conv_id=%s", conv_id)


@router.post("/chat")
async def chat(
    kb: Annotated[dict, Depends(get_user_kb)],
    conv: Annotated[dict, Depends(get_user_conv)],
    req: ChatRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "问题不能为空")

    kb_id = kb["id"]
    conv_id = conv["id"]

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
        full_sources = []
        sources_emitted = False
        needs_retrieval = True  # updated by classify_query node

        # With llm.astream(), each chunk is an individual token.
        # MiMo streams reasoning tokens first, then content tokens.
        # Emit reasoning immediately; buffer first 300 chars of content
        # to detect/strip JSON metadata — but ONLY for retrieval queries
        # where the LLM may inject JSON grades.  For non-retrieval queries
        # (simple chat), emit tokens directly so the user sees streaming.
        _strip_buf = ""
        _strip_buf_limit = 300
        _strip_emitting = False

        try:
            # Immediately emit user message so frontend can display it right away
            yield (
                f"event: user_message\ndata: {json.dumps({'role': 'user', 'content': query})}\n\n"
            )

            async for mode, data in stream_chat(query, kb_id, conv_id, history=history_msgs):
                if mode == "updates":
                    update_dict: dict = data

                    # classify_query determines whether retrieval is needed
                    if "classify_query" in update_dict and not sources_emitted:
                        needs_retrieval = update_dict["classify_query"].get("needs_retrieval", True)
                        if needs_retrieval:
                            # Notify frontend that retrieval is starting
                            yield f"event: searching\ndata: {json.dumps({'status': 'started'})}\n\n"
                        else:
                            # Non-retrieval query: send empty sources immediately
                            yield f"event: sources\ndata: {json.dumps({'sources': []})}\n\n"
                            sources_emitted = True

                    if "retrieve" in update_dict and not sources_emitted:
                        docs = update_dict["retrieve"].get("retrieved_docs", [])
                        sources = build_sources(docs)
                        full_sources = sources  # Save for database persistence
                        yield f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"
                        sources_emitted = True

                elif mode == "messages":
                    chunk, metadata = data

                    # Skip LLM chunks from non-answer nodes (classify, retrieve,
                    # grade, verify, refine all use ainvoke but graph.astream
                    # with stream_mode="messages" intercepts their LLM calls too).
                    # LangGraph metadata dict contains "langgraph_node" key.
                    node_name = ""
                    if isinstance(metadata, dict):
                        node_name = metadata.get("langgraph_node", "")
                    if node_name not in ("generate_answer", ""):
                        continue

                    # Reasoning tokens — emit immediately
                    reasoning_token = chunk.additional_kwargs.get("reasoning_content", "")
                    if not reasoning_token:
                        reasoning_token = chunk.additional_kwargs.get("reasoning", "")
                    if reasoning_token:
                        full_reasoning += reasoning_token
                        yield (
                            f"event: reasoning\ndata: {json.dumps({'token': reasoning_token})}\n\n"
                        )

                    # Content tokens — buffer first 300 chars to strip JSON metadata
                    # ONLY for retrieval queries. Non-retrieval queries (simple
                    # chat) have no JSON metadata, so emit directly for real-time
                    # streaming instead of buffering the entire short answer.
                    content_token = chunk.content
                    if content_token:
                        full_answer += content_token

                        if not needs_retrieval:
                            # Non-retrieval: emit directly, no buffering
                            yield (
                                f"event: answer\ndata: {json.dumps({'token': content_token})}\n\n"
                            )
                        elif not _strip_emitting:
                            _strip_buf += content_token
                            if len(_strip_buf) >= _strip_buf_limit:
                                stripped = strip_answer(_strip_buf)
                                if stripped:
                                    yield (
                                        f"event: answer\n"
                                        f"data: {json.dumps({'token': stripped})}\n\n"
                                    )
                                _strip_emitting = True
                                _strip_buf = ""
                        else:
                            clean = strip_answer(content_token)
                            if clean:
                                yield (f"event: answer\ndata: {json.dumps({'token': clean})}\n\n")

            # Flush remaining buffer
            if _strip_buf and not _strip_emitting:
                stripped = strip_answer(_strip_buf)
                if stripped:
                    yield (f"event: answer\ndata: {json.dumps({'token': stripped})}\n\n")

            # After streaming: strip internal data for the saved answer
            clean_answer = strip_answer(full_answer)
            if not clean_answer and full_answer:
                clean_answer = "根据现有文档无法提供详细回答。"

            # Save the clean answer to database (including sources for future reference)
            await MessageRepository.add_message(
                conversation_id=conv_id,
                role="assistant",
                content=clean_answer,
                reasoning_content=full_reasoning,
                sources=full_sources,
            )

            # Generate conversation title asynchronously for first message
            # Start task but don't block - title_update arrives after done
            conv = await ConvRepository.get(conv_id)
            title_task = None
            title_queue = None
            if conv and conv.get("title") == "新对话":
                title_queue = asyncio.Queue()
                title_task = asyncio.create_task(
                    _generate_title_async(conv_id, query, clean_answer, title_queue)
                )

            # Send done event immediately (don't wait for title)
            yield (
                f"event: done\n"
                f"data: {json.dumps({'reasoning': full_reasoning, 'answer': clean_answer})}\n\n"
            )

            # Briefly wait for title (max 2s) then send if available
            # Don't block the SSE stream for too long
            if title_task is not None:
                try:
                    # Wait up to 2 seconds - if title isn't ready, skip it
                    await asyncio.wait_for(title_task, timeout=2.0)
                    while title_queue and not title_queue.empty():
                        event_type, event_data = await title_queue.get()
                        yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"
                except TimeoutError:
                    # Title generation is slow - it will complete in background
                    # and update the DB, frontend will get title on next page load
                    logger.info(
                        "Title generation still in progress, skipping SSE event: conv_id=%s",
                        conv_id,
                    )
                except Exception:
                    logger.exception("Title generation failed: conv_id=%s", conv_id)

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
