"""Query classifier node — analyzes the user query and determines retrieval strategy.

Classifies queries into four types:
- factual:    direct factual questions (who, what, when, where)
- analytical: requires reasoning or explanation (why, how)
- multi_hop:  needs information from multiple document sections
- summary:    asks for overview or synthesis of broad topics

Sets search_strategy with:
- use_hyde: whether to use Hypothetical Document Embedding
- multi_query_count: number of query variations to generate (1 = disabled)

Uses DashScope qwen-flash for fast classification (low latency).
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

_CLASSIFIER_PROMPT = """分析用户问题，判断是否需要从知识库检索文档回答。

needs_retrieval=false: 日常闲聊、通用常识、指令类问题
needs_retrieval=true: 知识库相关、技术问题、需要引用文档

输出JSON: {"needs_retrieval": bool, "query_type": "factual|analytical|multi_hop|summary",
          "use_hyde": bool, "multi_query_count": int}

## 分类规则
- factual: 简单事实查询（谁/什么/何时/何地），multi_query_count=1, use_hyde=false
- analytical: 需要推理或解释（为什么/如何），multi_query_count=3, use_hyde=true
- multi_hop: 需要从多个文档段落获取信息，multi_query_count=3, use_hyde=true
- summary: 要求对 broad 主题进行概述，multi_query_count=2, use_hyde=false

## 示例
问题: 你好
输出: {"needs_retrieval": false, "query_type": "factual", "use_hyde": false, "multi_query_count": 1}

问题: 帮我写一段代码
输出: {"needs_retrieval": false, "query_type": "factual", "use_hyde": false, "multi_query_count": 1}

问题: SEEDER的全称是什么？
输出: {"needs_retrieval": true, "query_type": "factual", "use_hyde": false, "multi_query_count": 1}

问题: 为什么RAG需要reranker？
输出: {"needs_retrieval": true, "query_type": "analytical",
      "use_hyde": true, "multi_query_count": 3}

问题: 总结这篇论文的主要贡献
输出: {"needs_retrieval": true, "query_type": "summary", "use_hyde": false, "multi_query_count": 2}

问题: SEEDER和RAGAS在评估方法上有什么区别？
输出: {"needs_retrieval": true, "query_type": "multi_hop", "use_hyde": true, "multi_query_count": 3}

只输出JSON。"""


from app.llm_cache import get_dashscope_llm  # noqa: E402


def _get_llm() -> ChatOpenAI:
    """Get DashScope qwen-flash for fast classification."""
    return get_dashscope_llm(temperature=0)


def _parse_classification(raw: str) -> dict:
    """Parse LLM output as JSON, with fallback defaults."""
    try:
        # Extract JSON from possible markdown code block
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        qtype = data.get("query_type", "factual")
        if qtype not in ("factual", "analytical", "multi_hop", "summary"):
            qtype = "factual"
        return {
            "needs_retrieval": bool(data.get("needs_retrieval", True)),
            "query_type": qtype,
            "use_hyde": bool(data.get("use_hyde", False)),
            "multi_query_count": int(data.get("multi_query_count", 1)),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("Failed to parse classification: %s", raw[:200])
        return {
            "needs_retrieval": True,
            "query_type": "factual",
            "use_hyde": False,
            "multi_query_count": 1,
        }


async def classify_query(state: AgentState) -> dict:
    """Classify the user query and determine retrieval strategy."""
    query = state["query"]

    llm = _get_llm()
    messages = [
        SystemMessage(content=_CLASSIFIER_PROMPT),
        HumanMessage(content=f"问题: {query}"),
    ]

    try:
        response = await llm.ainvoke(messages)
        raw = response.content or ""
        result = _parse_classification(raw)
    except Exception:
        logger.exception("Query classification failed, using defaults")
        result = {
            "needs_retrieval": True,
            "query_type": "factual",
            "use_hyde": False,
            "multi_query_count": 1,
        }

    return {
        "needs_retrieval": result["needs_retrieval"],
        "query_type": result["query_type"],
        "search_strategy": {
            "use_hyde": result["use_hyde"],
            "multi_query_count": result["multi_query_count"],
        },
        "original_query": query,
    }
