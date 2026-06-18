from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ---- 基础字段（原有） ----
    messages: Annotated[list[BaseMessage], add_messages]
    kb_id: str
    query: str
    retrieved_docs: list[dict]
    reasoning: str
    answer: str
    sources: list[dict]

    # ---- Agentic RAG 扩展字段 ----
    # 查询分类
    query_type: str  # "factual" | "analytical" | "multi_hop" | "summary"
    needs_retrieval: bool  # 是否需要检索知识库
    search_strategy: dict  # 检索策略参数 (use_hyde, multi_query_count, etc.)

    # 查询改写（保留用于向后兼容，当前未使用）
    original_query: str  # 原始查询

    # 答案质量
    quality_score: float  # 答案质量分数 (0-1)
    verify_feedback: str  # 验证反馈（改进建议）
    needs_refine: bool  # 是否需要精炼
