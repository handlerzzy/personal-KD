"""Answer verifier node — validates answer quality against source documents.

Supports gradient verification based on query type:
- analytical: completeness only (medium risk, faster)
- multi_hop: faithfulness + completeness (high risk, thorough)

Outputs a quality score (0-1) and feedback for refinement.
If score < threshold, sets needs_refine=True to trigger refinement.
"""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState
from app.answer_cleaner import strip_answer

logger = logging.getLogger(__name__)

# Gradient verification thresholds
_VERIFICATION_THRESHOLDS = {
    "analytical": 0.6,  # More lenient for analytical queries
    "multi_hop": 0.7,  # Stricter for multi-hop queries
}

# Prompt for completeness-only verification (used for analytical queries)
_COMPLETENESS_PROMPT = """你是一个答案完整性验证专家。验证答案是否完整回答了问题。

## 评估维度
**完整性**（completeness）: 答案是否覆盖了问题的所有方面？是否遗漏关键信息？

## 输出格式（严格 JSON）
{
  "completeness_score": 0.0-1.0,
  "missing_points": ["遗漏点1", "遗漏点2"],
  "suggestion": "改进建议"
}

## 评分标准
- 1.0: 完整覆盖，无遗漏
- 0.7-0.9: 基本完整，有小遗漏
- 0.4-0.6: 部分完整，有明显遗漏
- 0.0-0.3: 严重不完整

只输出 JSON，不要其他内容。"""

# Prompt for full verification (used for multi-hop queries)
_FULL_VERIFICATION_PROMPT = """你是一个答案质量验证专家。
验证生成的答案是否基于检索文档，以及是否完整回答了问题。

## 评估维度
1. **有据性**（faithfulness）: 答案中的每个事实陈述是否都能在参考文档中找到依据？
2. **完整性**（completeness）: 答案是否完整回答了问题的所有方面？

## 输出格式（严格 JSON）
{
  "faithfulness_score": 0.0-1.0,
  "completeness_score": 0.0-1.0,
  "overall_score": 0.0-1.0,
  "issues": ["问题1", "问题2"],
  "suggestion": "改进建议"
}

## 评分标准
- 1.0: 完美，无问题
- 0.7-0.9: 良好，有小问题
- 0.4-0.6: 一般，有明显问题
- 0.0-0.3: 差，严重问题

只输出 JSON，不要其他内容。"""


from app.llm_cache import get_simple_llm  # noqa: E402


def _get_llm() -> ChatOpenAI:
    """Get cached verifier LLM."""
    return get_simple_llm(temperature=0, streaming=False)


def _parse_verification(raw: str, verification_type: str = "full") -> dict:
    """Parse LLM verification output.

    Args:
        raw: Raw LLM output (JSON string)
        verification_type: "full" for faithfulness+completeness,
            "completeness" for completeness only

    Returns:
        dict with quality_score, feedback, needs_refine
    """
    try:
        text = raw.strip()
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1).strip()
        else:
            # Try to find the last complete JSON object
            brace_start = text.rfind("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                text = text[brace_start : brace_end + 1]

        data = json.loads(text)

        if verification_type == "completeness":
            # Completeness-only verification (for analytical queries)
            completeness_score = float(data.get("completeness_score", 0.5))
            missing_points = data.get("missing_points", [])
            feedback = data.get("suggestion", "")
            if missing_points:
                feedback = f"遗漏: {', '.join(missing_points)}. {feedback}"
            return {
                "quality_score": completeness_score,
                "feedback": feedback,
                "needs_refine": completeness_score < _VERIFICATION_THRESHOLDS["analytical"],
            }
        else:
            # Full verification (for multi-hop queries)
            overall_score = float(data.get("overall_score", 0.5))
            return {
                "quality_score": overall_score,
                "feedback": data.get("suggestion", ""),
                "needs_refine": overall_score < _VERIFICATION_THRESHOLDS["multi_hop"],
            }
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("Failed to parse verification: %s", raw[:200])
        return {
            "quality_score": 0.5,
            "feedback": "验证结果解析失败",
            "needs_refine": False,
        }


async def verify_answer(state: AgentState) -> dict:
    """Verify answer quality against source documents.

    Gradient verification based on query_type:
    - analytical: completeness only (faster, more lenient)
    - multi_hop: faithfulness + completeness (thorough, stricter)
    """
    query = state["query"]
    query_type = state.get("query_type", "multi_hop")
    answer = state.get("answer", "")
    docs = state.get("retrieved_docs", [])

    if not answer:
        return {
            "quality_score": 0.0,
            "verify_feedback": "无答案可验证",
            "needs_refine": False,
        }

    # Build context from documents
    context_parts = []
    for i, doc in enumerate(docs):
        text = doc.get("text", "")[:300]
        context_parts.append(f"[{i + 1}] {text}")
    context = "\n\n".join(context_parts) if context_parts else "无参考文档"

    user_msg = f"## 问题\n{query}\n\n## 参考文档\n{context}\n\n## 待验证答案\n{answer}"

    # Gradient: choose prompt and verification type based on query_type
    if query_type == "analytical":
        prompt = _COMPLETENESS_PROMPT
        verification_type = "completeness"
        logger.info("Analytical query: completeness-only verification")
    else:
        prompt = _FULL_VERIFICATION_PROMPT
        verification_type = "full"
        logger.info("Multi-hop query: full verification (faithfulness + completeness)")

    llm = _get_llm()
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=user_msg),
    ]

    try:
        response = await llm.ainvoke(messages)
        raw = response.content or ""
        result = _parse_verification(raw, verification_type)
    except Exception:
        logger.exception("Answer verification failed")
        result = {
            "quality_score": 0.5,
            "feedback": "验证过程异常",
            "needs_refine": False,
        }

    return {
        "quality_score": result["quality_score"],
        "verify_feedback": result["feedback"],
        "needs_refine": result["needs_refine"],
    }


async def refine_answer(state: AgentState) -> dict:
    """Refine the answer based on verification feedback."""
    query = state["query"]
    answer = state.get("answer", "")
    feedback = state.get("verify_feedback", "")
    docs = state.get("retrieved_docs", [])

    # Build context
    context_parts = []
    for i, doc in enumerate(docs):
        text = doc.get("text", "")[:300]
        context_parts.append(f"[{i + 1}] {text}")
    context = "\n\n".join(context_parts) if context_parts else "无参考文档"

    refine_prompt = (
        "你是答案精炼专家。根据验证反馈改进答案。\n\n"
        "## 要求\n"
        "1. 修正不准确的表述，确保每个陈述都有文档依据\n"
        "2. 补充遗漏的信息\n"
        "3. 保持简洁，不要过度扩展\n"
        "4. 引用来源时标注编号\n"
        "5. 用中文回答"
    )

    user_msg = (
        f"## 原始问题\n{query}\n\n"
        f"## 参考文档\n{context}\n\n"
        f"## 当前答案\n{answer}\n\n"
        f"## 验证反馈\n{feedback}\n\n"
        f"请根据反馈改进答案。"
    )

    llm = _get_llm()
    llm_messages = [
        SystemMessage(content=refine_prompt),
        HumanMessage(content=user_msg),
    ]

    try:
        response = await llm.ainvoke(llm_messages)
        refined = (response.content or "").strip()
        if not refined:
            refined = answer
        # Strip any internal data that leaked into the refined answer
        refined = strip_answer(refined)
    except Exception:
        logger.exception("Answer refinement failed")
        refined = answer

    # Replace the last AIMessage in messages with the refined answer
    # so that streaming picks up the refined content
    messages = list(state.get("messages", []))
    if messages and isinstance(messages[-1], AIMessage):
        # Get the ID of the last AIMessage to replace it
        msg_id = messages[-1].id
        refined_msg = AIMessage(content=refined, id=msg_id)
        messages[-1] = refined_msg
    else:
        messages.append(AIMessage(content=refined))

    return {
        "answer": refined,
        "needs_refine": False,
        "messages": messages,
    }
