"""Query classifier node — analyzes the user query and determines retrieval strategy.

Classifies queries into five types:
- factual:    direct factual questions (who, what, when, where)
- analytical: requires reasoning or explanation (why, how)
- multi_hop:  needs information from multiple document sections
- summary:    asks for overview or synthesis of broad topics
- chitchat:   casual conversation or generic instructions

Design principle — "LLM qualifies, code quantifies":
  LLM only handles *qualitative* classification (query_type + intent).
  *Quantitative* strategy params (use_hyde, multi_query_count) are
  determined by code via RETRIEVAL_STRATEGIES table — stable, testable,
  tunable without prompt changes.

Uses DashScope qwen-flash for fast classification (low latency).
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy mapping: intent → concrete retrieval parameters
# LLM picks the *type*, code picks the *numbers*.  This keeps the prompt
# simple, makes tuning a config change rather than a prompt re‑write, and
# prevents LLM from outputting absurd values (e.g. multi_query_count=99).
# ---------------------------------------------------------------------------
RETRIEVAL_STRATEGIES: dict[str, dict] = {
    "factual": {"use_hyde": False, "multi_query_count": 1},
    "analytical": {"use_hyde": True, "multi_query_count": 3},
    "multi_hop": {"use_hyde": True, "multi_query_count": 3},
    "summary": {"use_hyde": False, "multi_query_count": 2},
    "chitchat": {"use_hyde": False, "multi_query_count": 0},
    # Unknown type → conservative medium-intensity retrieval
    "default": {"use_hyde": False, "multi_query_count": 1},
}

_VALID_TYPES = frozenset(RETRIEVAL_STRATEGIES.keys())

# ---------------------------------------------------------------------------
# Prompt — qualitative only.  No numeric parameters, no use_hyde, no counts.
# ---------------------------------------------------------------------------
_CLASSIFIER_PROMPT = """你是一个个人知识库的查询路由器。分析用户问题，判断意图。

## 输出JSON格式
{
    "needs_retrieval": bool,
    "query_type": "factual|analytical|multi_hop|summary|chitchat",
    "reasoning": "简短的判断理由"
}

## 判定规则
1. **needs_retrieval=true**:
   - 涉及用户私有文档、特定技术细节、内部术语。
   - 分析类、对比类、总结类问题。
   - **指令类问题**：如果指令涉及特定库、特定环境或知识库中的代码风格，必须检索。
2. **needs_retrieval=false**:
   - 纯粹的日常问候、闲聊。
   - 完全通用的知识（如"Python的list怎么用"），且不涉及知识库特有的扩展。

## query_type 定义
- factual: 简单事实查询。
- analytical: 需要推理解释（为什么/如何）。
- multi_hop: 涉及多个实体的对比或交集。
- summary: 归纳总结。
- chitchat: 闲聊或通用指令。

## 示例
问题: 你好
输出: {"needs_retrieval": false, "query_type": "chitchat", "reasoning": "日常问候"}

问题: 帮我写一段 Python 排序代码
输出: {"needs_retrieval": false, "query_type": "chitchat", "reasoning": "通用编程常识"}

问题: 帮我写一段基于 SEEDER 的评估脚本
输出: {"needs_retrieval": true, "query_type": "factual", "reasoning": "涉及特定术语SEEDER"}

问题: 为什么我的 RAG 检索效果不好？
输出: {"needs_retrieval": true, "query_type": "analytical", "reasoning": "需要结合知识库排查问题"}

问题: SEEDER和RAGAS在评估方法上有什么区别？
输出: {"needs_retrieval": true, "query_type": "multi_hop", "reasoning": "对比两个实体差异"}

问题: 总结一下你检索到的文档
输出: {"needs_retrieval": true, "query_type": "summary", "reasoning": "需要对已检索内容归纳"}

只输出JSON。"""


from app.llm_cache import get_dashscope_llm  # noqa: E402


def _get_llm() -> ChatOpenAI:
    """Get DashScope qwen-flash for fast classification."""
    return get_dashscope_llm(temperature=0)


def _parse_classification(raw: str) -> dict:
    """Parse LLM output, mapping intent to retrieval strategies.

    Strategy: LLM does *qualitative* classification (query_type),
    code does *quantitative* mapping (use_hyde, multi_query_count).
    This keeps retrieval behavior stable, testable, and tunable
    without prompt modifications.
    """
    # Default: assume retrieval needed (safe fallback to avoid missing answers)
    default_result = {
        "needs_retrieval": True,
        "query_type": "factual",
        **RETRIEVAL_STRATEGIES["default"],
        "reasoning": "",
    }

    try:
        # 1. Strip Markdown code‑block fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:].lstrip()
                if text.endswith("```"):
                    text = text[:-3].rstrip()

        data = json.loads(text)

        # 2. Validate query_type against known strategies
        qtype = data.get("query_type", "factual")
        if qtype not in _VALID_TYPES:
            qtype = "factual"

        # 3. Code decides strategy, NOT the LLM output
        strategy = RETRIEVAL_STRATEGIES.get(qtype, RETRIEVAL_STRATEGIES["default"])

        # 4. Chitchat forces needs_retrieval=false regardless of LLM output
        needs_retrieval = bool(data.get("needs_retrieval", True))
        if qtype == "chitchat":
            needs_retrieval = False

        return {
            "needs_retrieval": needs_retrieval,
            "query_type": qtype,
            "use_hyde": strategy["use_hyde"],
            "multi_query_count": strategy["multi_query_count"],
            "reasoning": data.get("reasoning", ""),
        }

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to parse classification: %s. Raw: %s", e, raw[:200])
        return default_result


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
            **RETRIEVAL_STRATEGIES["default"],
            "reasoning": "",
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
