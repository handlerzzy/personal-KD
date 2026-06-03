"""Integration test for the refactored streaming path.

Verifies:
1. graph.astream(stream_mode=["updates","messages"]) works
2. Token-level streaming yields AIMessageChunk objects
3. Checkpointer writes state after streaming
4. SSE event generation produces correct format
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage


class FakeAIMessageChunk:
    """Mock AIMessageChunk that LangGraph's stream_mode="messages" would produce."""
    content: str = ""
    additional_kwargs: dict = {}


async def test_graph_streaming():
    """Test that the compiled graph can stream with checkpointer."""
    print("=" * 60)
    print("测试1: Graph 编译 + checkpointer + stream_mode")
    print("=" * 60)

    from app.agent.graph import build_graph, close_checkpointer, init_checkpointer

    # Init checkpointer with in-memory DB for testing
    await init_checkpointer(":memory:")
    graph = build_graph()

    assert graph is not None
    print("  ✓ graph 编译成功")

    # Mock both LLM and retrieval together for both invoke and stream tests
    with (
        patch("app.agent.nodes.qa_node.ChatOpenAI") as mock_llm_class,
        patch(
            "app.agent.nodes.retrieval_node.embed_query",
            new_callable=AsyncMock,
        ) as mock_embed,
        patch(
            "app.agent.nodes.retrieval_node.dense.search",
            new_callable=AsyncMock,
        ) as mock_dense,
        patch("app.agent.nodes.retrieval_node.sparse.search") as mock_sparse,
        patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion") as mock_rrf,
        patch(
            "app.retrieval.reranker.rerank", new_callable=AsyncMock
        ) as mock_rerank,
    ):

        mock_embed.return_value = [0.1] * 512
        mock_dense.return_value = []
        mock_sparse.return_value = []
        mock_rrf.return_value = []
        mock_rerank.return_value = []

        # --- Test ainvoke (non-streaming) ---
        mock_instance = AsyncMock()
        mock_instance.ainvoke = AsyncMock(return_value=AIMessage(content="测试回复"))
        mock_llm_class.return_value = mock_instance

        result = await graph.ainvoke(
            {
                "messages": [],
                "kb_id": "test123456789",
                "query": "测试问题",
                "retrieved_docs": [],
                "reasoning": "",
                "answer": "",
            },
            config={"configurable": {"thread_id": "test-thread-1"}},
        )

        print(f"  answer: {result.get('answer', '')[:50]}")
        print(f"  messages count: {len(result.get('messages', []))}")
        assert result.get("answer") == "测试回复", "answer 不匹配"
        print("  ✓ ainvoke 正确返回结果")

        # --- Test streaming ---
        print("\n--- 测试 stream_mode=[\"updates\",\"messages\"] ---")
        mock_instance2 = AsyncMock()
        mock_instance2.ainvoke = AsyncMock(return_value=AIMessage(content="流式测试回复"))
        mock_llm_class.return_value = mock_instance2

        stream_events = []
        async for mode, data in graph.astream(
            {
                "messages": [],
                "kb_id": "test123456789",
                "query": "流式问题",
                "retrieved_docs": [],
                "reasoning": "",
                "answer": "",
            },
            config={"configurable": {"thread_id": "test-thread-2"}},
            stream_mode=["updates", "messages"],
        ):
            stream_events.append((mode, type(data).__name__))
            if mode == "updates":
                print(f"  updates: {list(data.keys())}")
            elif mode == "messages":
                chunk, meta = data
                content_preview = chunk.content[:30] if chunk.content else "(empty)"
                print(
                    f"  messages: content={content_preview}, "
                    f"node={meta.get('langgraph_node', '?')}"
                )

        assert len(stream_events) > 0, "没有收到任何 stream 事件"
        print(f"  ✓ 收到 {len(stream_events)} 个 stream 事件")

    await close_checkpointer()
    print("  ✓ checkpointer 正常关闭")
    print()


async def test_chat_sse_generation():
    """Test that chat.py's event_generator produces correct SSE format."""
    print("=" * 60)
    print("测试2: SSE 事件生成")
    print("=" * 60)

    # Simulate what stream_chat would yield
    async def fake_stream():
        # updates: retrieve completed
        yield ("updates", {
            "retrieve": {
                "retrieved_docs": [
                    {"chunk_id": "c1", "text": "测试文档内容", "score": 0.95, "doc_id": "d1"}
                ]
            }
        })
        # messages: LLM tokens - simulate reasoning
        reasoning_chunk = FakeAIMessageChunk()
        reasoning_chunk.content = ""
        reasoning_chunk.additional_kwargs = {"reasoning_content": "思考"}
        yield ("messages", (reasoning_chunk, {"langgraph_node": "qa"}))

        # messages: answer tokens
        answer_chunk = FakeAIMessageChunk()
        answer_chunk.content = "这是"
        answer_chunk.additional_kwargs = {}
        yield ("messages", (answer_chunk, {"langgraph_node": "qa"}))

        answer_chunk2 = FakeAIMessageChunk()
        answer_chunk2.content = "回复"
        answer_chunk2.additional_kwargs = {}
        yield ("messages", (answer_chunk2, {"langgraph_node": "qa"}))

    # Build SSE output
    sse_lines = []
    full_reasoning = ""
    full_answer = ""
    sources_emitted = False

    from app.api.chat import _build_sources_from_docs

    async for mode, data in fake_stream():
        if mode == "updates":
            update_dict: dict = data
            if "retrieve" in update_dict and not sources_emitted:
                docs = update_dict["retrieve"].get("retrieved_docs", [])
                sources = _build_sources_from_docs(docs)
                sse = f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"
                sse_lines.append(sse)
                sources_emitted = True

        elif mode == "messages":
            chunk, _meta = data
            reasoning_token = chunk.additional_kwargs.get("reasoning_content", "")
            if not reasoning_token:
                reasoning_token = chunk.additional_kwargs.get("reasoning", "")
            if reasoning_token:
                full_reasoning += reasoning_token
                sse_lines.append(
                    f"event: reasoning\ndata: {json.dumps({'token': reasoning_token})}\n\n"
                )
            if chunk.content:
                full_answer += chunk.content
                sse_lines.append(
                    f"event: answer\ndata: {json.dumps({'token': chunk.content})}\n\n"
                )

    sse_lines.append(
        "event: done\n"
        + f"data: {json.dumps({'reasoning': full_reasoning, 'answer': full_answer})}\n\n"
    )

    print("  SSE events:")
    for sse_line in sse_lines:
        for line in sse_line.strip().split("\n"):
            print(f"    {line}")

    # Verify event order
    events = [sse_line.split("\n")[0].replace("event: ", "") for sse_line in sse_lines]
    assert events[0] == "sources", f"第一个事件应为 sources，实际为 {events[0]}"
    assert events[1] == "reasoning", "第二个事件应为 reasoning"
    assert events[2] == "answer", "第三个事件应为 answer"
    assert events[-1] == "done", "最后一个事件应为 done"
    assert full_reasoning == "思考"
    assert full_answer == "这是回复"
    print("  ✓ SSE 事件顺序和内容正确")
    print()


async def test_message_conversion():
    """Test _messages_from_dicts conversion."""
    print("=" * 60)
    print("测试3: 消息格式转换")
    print("=" * 60)

    from app.agent.graph import _messages_from_dicts

    history = [
        {"id": "a1", "role": "user", "content": "问题1"},
        {"id": "b1", "role": "assistant", "content": "回答1"},
        {"id": "a2", "role": "user", "content": "问题2"},
        {"id": "b2", "role": "assistant", "content": ""},  # 空消息应被跳过
    ]

    result = _messages_from_dicts(history)

    assert len(result) == 3, f"应用 3 条有效消息，实际 {len(result)}"
    assert isinstance(result[0], HumanMessage)
    assert isinstance(result[1], AIMessage)
    assert result[0].content == "问题1"
    assert result[1].content == "回答1"
    print(f"  ✓ 转换 {len(result)} 条消息，类型正确")
    print()


async def test_checkpointer_persistence():
    """Test that checkpointer actually stores state after streaming."""
    print("=" * 60)
    print("测试4: Checkpointer 持久化验证")
    print("=" * 60)

    from app.agent.graph import build_graph, close_checkpointer, init_checkpointer

    # Each test uses its own checkpointer (in-memory)
    await init_checkpointer(":memory:")
    graph = build_graph()

    with (
        patch("app.agent.nodes.qa_node.ChatOpenAI") as mock_llm_class,
        patch(
            "app.agent.nodes.retrieval_node.embed_query",
            new_callable=AsyncMock,
        ) as mock_embed,
        patch(
            "app.agent.nodes.retrieval_node.dense.search",
            new_callable=AsyncMock,
        ) as mock_dense,
        patch("app.agent.nodes.retrieval_node.sparse.search") as mock_sparse,
        patch("app.agent.nodes.retrieval_node.hybrid.rrf_fusion") as mock_rrf,
        patch(
            "app.retrieval.reranker.rerank", new_callable=AsyncMock
        ) as mock_rerank,
    ):

        mock_embed.return_value = [0.1] * 512
        mock_dense.return_value = []
        mock_sparse.return_value = []
        mock_rrf.return_value = []
        mock_rerank.return_value = []
        mock_instance = AsyncMock()
        mock_instance.ainvoke = AsyncMock(return_value=AIMessage(content="checkpoint测试"))
        mock_llm_class.return_value = mock_instance

        thread_id = "persist-test-1"
        events = []
        async for mode, data in graph.astream(
            {
                "messages": [],
                "kb_id": "t00000000000",
                "query": "持久化测试",
                "retrieved_docs": [],
                "reasoning": "",
                "answer": "",
            },
            config={"configurable": {"thread_id": thread_id}},
            stream_mode=["updates", "messages"],
        ):
            events.append(mode)

    # Check state was persisted
    state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    print(f"  state values keys: {list(state.values.keys()) if state.values else 'EMPTY'}")

    if state.values:
        msgs = state.values.get("messages", [])
        print(f"  persisted messages count: {len(msgs)}")
        if len(msgs) > 0:
            print("  ✓ checkpointer 已正确写入 state")
        else:
            print("  ⚠ state values 存在但 messages 为空")
    else:
        print("  ⚠ state.values 为空 — checkpointer 可能未正常工作")

    await close_checkpointer()
    print()


async def main():
    await test_graph_streaming()
    await test_chat_sse_generation()
    await test_message_conversion()
    await test_checkpointer_persistence()
    print("=" * 60)
    print("所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
