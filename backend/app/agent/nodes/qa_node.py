from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage

from app.agent.state import AgentState
from app.config import settings


async def qa_node(state: AgentState) -> dict:
    """Generate answer using LLM with retrieved context."""
    query = state["query"]
    docs = state.get("retrieved_docs", [])

    # Build context from retrieved docs
    context = "\n\n".join([
        f"[{i+1}] {d['text']}"
        for i, d in enumerate(docs)
    ]) if docs else "未找到相关文档。"

    system_prompt = (
        "你是一个知识库问答助手。基于以下检索到的文档内容回答问题。\n"
        "如果你不知道答案，请直接说不知道，不要编造。\n"
        "引用来源时标注编号。请用中文回答。\n\n"
        f"参考文档：\n{context}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    # Call LLM API (OpenAI-compatible)
    import httpx
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.llm_api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": messages,
                "stream": False,
            },
        )
        data = response.json()
        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")
        reasoning = choice.get("message", {}).get("reasoning_content", "")

    # Build sources list
    sources = []
    for d in docs:
        sources.append({
            "chunk_id": d.get("chunk_id", ""),
            "text": d.get("text", "")[:200],
            "score": round(d.get("score", 0.0), 4),
            "doc_id": d.get("doc_id", ""),
        })

    return {
        "answer": content,
        "reasoning": reasoning,
        "sources": sources,
        "messages": [AIMessage(content=content)],
    }


async def qa_node_stream(state: AgentState) -> AsyncGenerator[dict, None]:
    """Stream answer from LLM token by token (SSE)."""
    query = state["query"]
    docs = state.get("retrieved_docs", [])

    context = "\n\n".join([
        f"[{i+1}] {d['text']}"
        for i, d in enumerate(docs)
    ]) if docs else "未找到相关文档。"

    system_prompt = (
        "你是一个知识库问答助手。基于以下检索到的文档内容回答问题。\n"
        "如果你不知道答案，请直接说不知道，不要编造。\n"
        "引用来源时标注编号。请用中文回答。\n\n"
        f"参考文档：\n{context}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    # Sources ahead of answer
    sources = []
    for d in docs:
        sources.append({
            "chunk_id": d.get("chunk_id", ""),
            "text": d.get("text", "")[:200],
            "score": round(d.get("score", 0.0), 4),
            "doc_id": d.get("doc_id", ""),
        })
    yield {"type": "sources", "data": json.dumps({"sources": sources})}

    # Stream from LLM
    import httpx
    full_reasoning = ""
    full_answer = ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.llm_api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": messages,
                "stream": True,
            },
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                delta = chunk.get("choices", [{}])[0].get("delta", {})
                # Reasoning content
                if "reasoning_content" in delta and delta["reasoning_content"]:
                    token = delta["reasoning_content"]
                    full_reasoning += token
                    yield {"type": "reasoning", "data": json.dumps({"token": token})}
                # Answer content
                if "content" in delta and delta["content"]:
                    token = delta["content"]
                    full_answer += token
                    yield {"type": "answer", "data": json.dumps({"token": token})}

    yield {"type": "done", "data": json.dumps({"reasoning": full_reasoning, "answer": full_answer})}
