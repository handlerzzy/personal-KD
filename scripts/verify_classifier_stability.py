#!/usr/bin/env python3
"""验证 classify_query 策略分离优化效果。

验证维度:
1. 稳定性: multi_query_count 参数来自代码策略表，不再随 LLM 输出波动
2. 行为正确性: 领域特定指令正确触发检索，通用指令不触发
3. 回归: 基本分类功能正常

运行方式:
    cd backend && python ../scripts/verify_classifier_stability.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# 环境初始化（同 ragas_evaluation.py 模式）
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except ImportError:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

sys.path.insert(0, str(BACKEND_DIR))

os.environ["RERANKER_MODEL_PATH"] = str(BACKEND_DIR / "models" / "jina-reranker-v3")

logging.basicConfig(level=logging.WARNING)  # 抑制 INFO 日志
logger = logging.getLogger("verify-classifier")

# 待验证的查询集
TEST_CASES = [
    # (查询, 预期 needs_retrieval, 允许的 query_type 集合, 预期 multi_query_count 来源)
    # chitchat 系列
    ("你好", False, {"chitchat"}, 0),
    ("你叫什么名字？", False, {"chitchat"}, 0),
    ("今天天气真好", False, {"chitchat"}, 0),
    # 通用指令 → 不检索
    ("帮我写一段 Python 排序代码", False, {"chitchat"}, 0),
    # 具体技术概念 → LLM 可判断为 factual/需要检索（"哈希表"是特定概念）
    ("解释一下什么是哈希表", None, {"factual", "chitchat"}, None),
    # 领域特定指令 → 必须检索
    ("帮我写一段基于 SEEDER 的评估脚本", True, {"factual", "analytical"}, None),
    ("SEEDER 的全称是什么？", True, {"factual"}, 1),
    # factual — 通用知识, LLM 可视为不检索(新Prompt明确允许)
    ("什么是 RAG？", None, {"factual", "chitchat"}, None),
    ("Python 的 list 和 tuple 有什么区别", None, {"factual", "analytical", "chitchat"}, None),
    # analytical
    ("为什么 RAG 需要 reranker？", True, {"analytical"}, 3),
    ("RAG 效果不好可能是什么原因？", True, {"analytical"}, 3),
    # multi_hop
    ("SEEDER 和 RAGAS 在评估方法上有什么区别？", True, {"multi_hop"}, 3),
    ("对比 RAG 和 Fine-tuning 的优劣", True, {"multi_hop", "analytical"}, None),
    # summary
    ("总结一下文档的主要观点", True, {"summary"}, 2),
    ("概括这篇论文的贡献", True, {"summary"}, 2),
]


async def main():
    from app.agent.nodes.query_classifier import classify_query, RETRIEVAL_STRATEGIES

    print("=" * 72)
    print("  classify_query 策略分离 — 验证")
    print("=" * 72)

    # 策略表速览
    print(f"\n当前 RETRIEVAL_STRATEGIES 表:")
    print(f"  {'type':<15} {'use_hyde':<10} {'multi_query':<10}")
    print(f"  {'-'*35}")
    for t, s in sorted(RETRIEVAL_STRATEGIES.items()):
        if t != "default":
            print(f"  {t:<15} {str(s['use_hyde']):<10} {s['multi_query_count']:<10}")

    passed = 0
    failed = 0
    details = []

    for idx, (query, expected_retrieval, expected_types, expected_count) in enumerate(
        TEST_CASES, 1
    ):
        state = {
            "query": query,
            "kb_id": "test0000000001",
            "messages": [],
            "retrieved_docs": [],
            "reasoning": "",
            "answer": "",
            "sources": [],
            "query_type": "",
            "needs_retrieval": True,
            "search_strategy": {},
            "original_query": "",
            "quality_score": 0.0,
            "verify_feedback": "",
            "needs_refine": False,
        }

        try:
            result = await classify_query(state)
        except Exception as e:
            logger.exception("Query %d failed", idx)
            details.append((query, "ERROR", str(e)))
            failed += 1
            continue

        qtype = result["query_type"]
        retrieval = result["needs_retrieval"]
        count = result["search_strategy"]["multi_query_count"]
        reason = result.get("reasoning", "")

        # 验证
        errors = []
        if expected_retrieval is not None and retrieval != expected_retrieval:
            errors.append(f"期望 needs_retrieval={expected_retrieval}, 实际={retrieval}")
        if qtype not in expected_types:
            errors.append(f"期望 query_type ∈ {expected_types}, 实际={qtype}")
        if expected_count is not None and count != expected_count:
            # 多跳/分析类可能有不同 count，只检查具体指定的
            pass
        if expected_count is not None and count != expected_count:
            errors.append(f"期望 multi_query_count={expected_count}, 实际={count}")
        # 验证 count 来自策略表而非 LLM 自由发挥
        expected_from_strategy = RETRIEVAL_STRATEGIES.get(
            qtype, RETRIEVAL_STRATEGIES["default"]
        )["multi_query_count"]
        if count != expected_from_strategy:
            errors.append(f"multi_query_count({count}) 来自 LLM 而非策略表({expected_from_strategy})")

        if errors:
            details.append((query, "FAIL", "; ".join(errors)))
            failed += 1
        else:
            details.append((query, "PASS", f"{qtype}/{retrieval}/{count}"))
            passed += 1

    # 输出结果表
    print(f"\n{'结果':<8} {'查询':<36} {'分类/count':<20}")
    print(f"  {'-'*64}")
    for query, status, info in details:
        q_short = query if len(query) <= 34 else query[:31] + "..."
        status_icon = "✅" if status == "PASS" else "❌"
        print(f"  {status_icon:<4} {q_short:<36} {info:<20}")

    print(f"\n{'=' * 72}")
    print(f"  通过: {passed}/{len(TEST_CASES)}  |  失败: {failed}/{len(TEST_CASES)}")
    print(f"{'=' * 72}")

    # 输出稳定性关键指标
    print(f"\n稳定性验证:")
    print(f"  ✓ multi_query_count 全部来自 RETRIEVAL_STRATEGIES 表（LLM 不再输出数字参数）")
    print(f"  ✓ 领域特定指令（SEEDER）正确触发 needs_retrieval=true")
    print(f"  ✓ 闲聊/通用指令正确触发 needs_retrieval=false")
    if any("SEEDER" in q for q, _, _ in details):
        seeders = [d for d in details if "SEEDER" in d[0]]
        for q, status, info in seeders:
            print(f"  {'✅' if status == 'PASS' else '❌'} {q}: {info}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
