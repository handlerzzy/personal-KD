"""
RAG 系统 RAGAS 专业评估脚本

评估维度：
- Faithfulness（有据性）：生成答案 vs 检索文档
- AnswerCorrectness（正确性）：生成答案 vs 标准答案
- ContextPrecision（检索相关性）：检索文档 vs 问题（参考标准答案）
- ContextRecall（召回完整性）：标准答案是否被检索文档覆盖

使用方式：
    cd backend && PYTHONPATH=. python ../scripts/rag_evaluation.py
    cd backend && PYTHONPATH=. python ../scripts/rag_evaluation.py --max-workers 8
    cd backend && PYTHONPATH=. python ../scripts/rag_evaluation.py --max-workers 14 --timeout 180
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 环境初始化
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
env_file = BACKEND_DIR / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(env_file, override=False)
except ImportError:
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip("\"'")
                os.environ.setdefault(key.strip(), value)

os.environ["RERANKER_MODEL_PATH"] = str(BACKEND_DIR / "models" / "jina-reranker-v3")
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ragas-eval")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

PDF_DIR = Path(__file__).resolve().parent.parent / "pdf"
QA_FILE = Path(__file__).resolve().parent.parent / "test_QA.md"
REPORT_DIR = Path(__file__).resolve().parent.parent / "evaluation_results"
TEST_KB_ID = "eval0000000001"  # 12-char hex for ID validation
EVAL_CONVERSATION_ID = "eval000000001"

_PROXY_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "SOCKS_PROXY", "socks_proxy",
)

PDF_MAP = {
    "第一篇论文": "2510.00001v1.pdf",
    "第二篇论文": "2605.23753v1.pdf",
    "第三篇论文": "2605.23754v1.pdf",
    "第四篇论文": "2605.23797v1.pdf",
    "第五篇论文": "2605.23825v1.pdf",
}


# ---------------------------------------------------------------------------
# 1. 解析 test_QA.md → 100 个 QA 对
# ---------------------------------------------------------------------------

def parse_qa_file(file_path: Path) -> list[dict]:
    """解析 test_QA.md，提取 100 个 QA 对及其来源论文。"""
    content = file_path.read_text(encoding="utf-8")
    qa_pairs = []

    # 按论文分节
    sections = re.split(r"(?=^## 第)", content, flags=re.MULTILINE)

    paper_names = [
        "第一篇论文",
        "第二篇论文",
        "第三篇论文",
        "第四篇论文",
        "第五篇论文",
    ]
    paper_idx = 0

    for section in sections:
        # 匹配论文名
        matched = False
        for pname in paper_names:
            if pname in section[:50]:
                matched = True
                break
        if not matched:
            continue

        # 提取 QA 对
        pattern = r"\*\*Q(\d+):\*\*\s*(.*?)\s*\n\s*\*\*A\d+:\*\*\s*(.*?)(?=\n\s*\*\*Q|\Z)"
        matches = re.findall(pattern, section, re.DOTALL)

        for num, question, answer in matches:
            clean_answer = re.sub(r"（来源：.*?）", "", answer).strip()
            qa_pairs.append({
                "id": f"QA_{int(num):02d}",
                "question": question.strip(),
                "answer": clean_answer,
                "paper_name": paper_names[paper_idx],
                "paper_pdf": PDF_MAP[paper_names[paper_idx]],
            })

        paper_idx += 1
        if paper_idx >= len(paper_names):
            break

    logger.info("解析到 %d 个 QA 对（来自 %d 篇论文）", len(qa_pairs), paper_idx)
    return qa_pairs


# ---------------------------------------------------------------------------
# 2. 创建知识库并上传 PDF
# ---------------------------------------------------------------------------

async def ensure_kb_ready(kb_id: str) -> str | None:
    """检查/创建知识库，返回实际的 KB ID。"""
    from app.retrieval import dense
    from app.persistence.kb_repo import KbRepository

    # 初始化 SQLite
    from app.persistence.database import set_db_path, init_db
    set_db_path(str(BACKEND_DIR / "data" / "agent.db"))
    await init_db()

    # 扫描所有 Qdrant 集合，找有数据的
    try:
        import logging as _lg
        _lg.getLogger("httpx").setLevel(_lg.WARNING)
        client = dense.get_client()
        collections = (await client.get_collections()).collections
        for col in collections:
            cname = col.name
            if not cname.startswith("kb_") or cname == "kb_None":
                continue
            cid = cname[3:]
            info = await client.get_collection(cname)
            if info.points_count > 0:
                existing = await KbRepository.get(cid)
                if existing:
                    logger.info("复用现有知识库: %s (%d 文档块)", cid, info.points_count)
                    return cid
                await KbRepository.create(name=cid[:12], description="Reused KB")
                logger.info("注册 Qdrant 集合到 SQLite: %s (%d 文档块)", cid, info.points_count)
                return cid
    except Exception:
        pass

    logger.info("未找到现有知识库，创建新库 ...")
    kb = await KbRepository.create(name="RAGAS Evaluation KB")
    aid = kb["id"]
    await dense.create_collection(aid)
    from app.retrieval import sparse
    sparse.create_index(aid)
    ok = await _upload_pdfs(aid)
    return aid if ok else None


async def _upload_pdfs(kb_id: str) -> bool:
    """上传 5 个 PDF 到知识库。"""
    from app.document.parser import parse_document
    from app.document.chunker import split_text
    from app.document.embedder import embed_texts
    from app.retrieval import dense, sparse

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.error("PDF 目录为空: %s", PDF_DIR)
        return False

    logger.info("找到 %d 个 PDF 文件，开始上传...", len(pdf_files))

    all_chunks, all_texts = [], []
    pdf_text_cache = {}

    for pdf_file in pdf_files:
        logger.info("解析 PDF: %s", pdf_file.name)
        try:
            text = await parse_document(str(pdf_file), file_type="pdf")
        except Exception:
            logger.exception("PDF 解析失败: %s", pdf_file.name)
            continue

        if not text:
            logger.warning("PDF 解析结果为空: %s", pdf_file.name)
            continue

        pdf_text_cache[pdf_file.name] = text

        chunks = split_text(text, kb_id=kb_id, doc_id=pdf_file.stem)
        all_chunks.extend(chunks)
        all_texts.extend(c["text"] for c in chunks)
        logger.info("  %s → %d 个文档块", pdf_file.name, len(chunks))

    if not all_chunks:
        logger.error("没有成功解析任何文档")
        return False

    logger.info("嵌入 %d 个文档块...", len(all_chunks))
    embeddings = await embed_texts(all_texts)

    await dense.upsert_chunks(kb_id, all_chunks, embeddings)
    sparse.add_documents(kb_id, all_texts)

    logger.info(
        "上传完成: %d 个文档块已存入 Qdrant + BM25",
        len(all_chunks),
    )
    return True


# ---------------------------------------------------------------------------
# 3. RAG 管道
# ---------------------------------------------------------------------------

async def _retry(coro_factory, max_retries=3, base_delay=2.0):
    """指数退避重试（应对 429 限流）。"""
    import random
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                delay = base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    "429 限流，%.1fs 后重试 (%d/%d)",
                    delay, attempt + 1, max_retries,
                )
                await asyncio.sleep(delay)
            else:
                raise


async def rag_invoke(question: str, kb_id: str) -> dict:
    """对单个问题执行完整 RAG 管线，返回答案和检索文档。"""
    from app.agent.graph import build_graph, init_checkpointer
    from app.agent.state import AgentState

    await init_checkpointer(str(BACKEND_DIR / "data" / "agent.db"))
    graph = build_graph()

    config = {"configurable": {"thread_id": f"eval_{hash(question) % 100000}"}}

    initial_state: AgentState = {
        "messages": [],
        "kb_id": kb_id,
        "query": question,
        "retrieved_docs": [],
        "reasoning": "",
        "answer": "",
    }

    result = await graph.ainvoke(initial_state, config=config)

    return {
        "answer": result.get("answer", ""),
        "retrieved_docs": result.get("retrieved_docs", []),
    }


# ---------------------------------------------------------------------------
# 4. RAGAS 评估
# ---------------------------------------------------------------------------

def get_ragas_llm():
    """创建 RAGAS 评估用 LLM（使用 DeepSeek，通过 OpenAI 兼容接口调用）。"""
    import openai
    from ragas.llms import llm_factory

    ds_base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    ds_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "")

    saved = {k: os.environ.pop(k) for k in _PROXY_KEYS if k in os.environ}
    try:
        client = openai.OpenAI(
            api_key=ds_key,
            base_url=ds_base,
        )
        logger.info("RAGAS 评估 LLM: %s (%s)", ds_model, ds_base)
        return llm_factory(
            model=ds_model,
            provider="openai",
            client=client,
            temperature=0,
        )
    finally:
        os.environ.update(saved)


def get_ragas_embeddings():
    """创建 RAGAS 评估用的 Embeddings（包装 ZhipuAIEmbeddings 支持异步）。"""
    from langchain_community.embeddings import ZhipuAIEmbeddings
    from ragas.embeddings.base import LangchainEmbeddingsWrapper
    from app.config import settings

    saved = {k: os.environ.pop(k) for k in _PROXY_KEYS if k in os.environ}
    try:
        lce = ZhipuAIEmbeddings(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            api_key=settings.zhipu_api_key,
        )
        return LangchainEmbeddingsWrapper(embeddings=lce)
    finally:
        os.environ.update(saved)


async def run_ragas_evaluation(dataset, *, max_workers=16, timeout=120):
    """使用 RAGAS 评估数据集。"""
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_correctness,
        context_precision,
        context_recall,
    )
    from ragas.run_config import RunConfig

    logger.info("初始化 RAGAS 评估 LLM...")
    llm = get_ragas_llm()
    embeddings = get_ragas_embeddings()

    run_config = RunConfig(
        max_workers=max_workers,
        timeout=timeout,
        max_retries=3,
        max_wait=15,
        log_tenacity=False,
    )

    metrics = [faithfulness, answer_correctness, context_precision, context_recall]

    logger.info(
        "开始 RAGAS 评估（共 %d 个样本, max_workers=%d, timeout=%ds）...",
        len(dataset.samples), max_workers, timeout,
    )
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
        run_config=run_config,
        show_progress=True,
        raise_exceptions=False,
    )

    return result


# ---------------------------------------------------------------------------
# 5. 报告生成
# ---------------------------------------------------------------------------

def generate_report(eval_result, qa_pairs: list[dict], total_time: float):
    """生成评估报告（Markdown + JSON）。"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    scores_df = eval_result.to_pandas()
    scores = {
        "faithfulness": scores_df["faithfulness"].tolist(),
        "answer_correctness": scores_df["answer_correctness"].tolist(),
        "context_precision": scores_df["context_precision"].tolist(),
        "context_recall": scores_df["context_recall"].tolist(),
    }

    # ---- 统计 ----
    stats = {}
    for metric_name, values in scores.items():
        valid = [v for v in values if v is not None and not (isinstance(v, float) and v != v)]
        stats[metric_name] = {
            "mean": round(sum(valid) / len(valid), 4) if valid else 0,
            "pass": sum(1 for v in valid if v >= 0.9),
            "fail": sum(1 for v in valid if v < 0.9),
            "total": len(valid),
        }

    # ---- Markdown 报告 ----
    lines = [
        "# RAG 系统评估报告（RAGAS）",
        "",
        f"**评估时间**: {timestamp}",
        f"**测试集大小**: {len(qa_pairs)} 个 QA 对",
        f"**评估耗时**: {total_time:.0f} 秒 ({total_time / 60:.1f} 分钟)",
        "",
        "## 评估指标",
        "",
        "| 指标 | 平均分 | ≥0.9 通过率 | 含义",
        "|------|--------|------------|------",
    ]

    metric_labels = {
        "faithfulness": "Faithfulness（有据性）",
        "answer_correctness": "AnswerCorrectness（正确性）",
        "context_precision": "ContextPrecision（检索相关性）",
        "context_recall": "ContextRecall（召回完整性）",
    }
    metric_meanings = {
        "faithfulness": "生成答案是否忠于检索文档（无幻觉）",
        "answer_correctness": "生成答案与标准答案的一致程度",
        "context_precision": "检索到的文档是否与问题相关",
        "context_recall": "标准答案的信息能否从检索文档中找到",
    }

    for m, label in metric_labels.items():
        s = stats[m]
        pass_rate = s["pass"] / s["total"] * 100 if s["total"] > 0 else 0
        status = "PASS" if pass_rate >= 90 else "WARN" if pass_rate >= 70 else "FAIL"
        lines.append(
            f"| {label} | {s['mean']:.3f} | {s['pass']}/{s['total']} ({pass_rate:.0f}%) {status} | {metric_meanings[m]} |"
        )

    # 按论文分组
    lines.extend(["", "## 按论文分组统计", ""])
    paper_groups = {}
    for qa in qa_pairs:
        pname = qa["paper_name"]
        if pname not in paper_groups:
            paper_groups[pname] = []
        paper_groups[pname].append(qa)

    lines.append("| 论文 | QQ数 | Faithfulness | Correctness | Precision | Recall |")
    lines.append("|------|------|-------------|-------------|-----------|--------|")

    # Build per-paper stats
    for pname, group_qas in paper_groups.items():
        n = len(group_qas)
        # Find indices for this paper's questions
        indices = []
        for idx, qa in enumerate(qa_pairs):
            if qa["paper_name"] == pname:
                indices.append(idx)

        pstats = {}
        for m in ["faithfulness", "answer_correctness", "context_precision", "context_recall"]:
            vals = [scores[m][i] for i in indices]
            valid = [v for v in vals if v is not None and not (isinstance(v, float) and v != v)]
            pstats[m] = round(sum(valid) / len(valid), 3) if valid else 0

        lines.append(
            f"| {pname} | {n} | {pstats['faithfulness']:.3f} | {pstats['answer_correctness']:.3f} | {pstats['context_precision']:.3f} | {pstats['context_recall']:.3f} |"
        )

    # 失败案例分析
    lines.extend(["", "## 失败案例分析", ""])
    for m, label in metric_labels.items():
        failed = []
        for idx, val in enumerate(scores[m]):
            if val is not None and not (isinstance(val, float) and val != val) and val < 0.9:
                failed.append((idx, val, qa_pairs[idx]))

        if failed:
            lines.append(f"### {label}（{len(failed)} 个失败）")
            lines.append("")
            for idx, val, qa in failed[:10]:
                q = qa["question"][:60] + ("..." if len(qa["question"]) > 60 else "")
                lines.append(f"- **{qa['id']}** ({qa['paper_name']}): {q} → {val:.3f}")
            if len(failed) > 10:
                lines.append(f"- ... 还有 {len(failed) - 10} 个失败")
            lines.append("")

    # 逐题详情
    lines.extend(["", "## 逐题详情", ""])
    lines.append("| ID | 论文 | F | C | P | R | 问题（前30字） |")
    lines.append("|-----|------|---|---|---|---|----------------|")
    for idx, qa in enumerate(qa_pairs):
        f = scores["faithfulness"][idx]
        c = scores["answer_correctness"][idx]
        p = scores["context_precision"][idx]
        r = scores["context_recall"][idx]

        def fmt(v):
            if v is None or (isinstance(v, float) and v != v):
                return "N/A"
            return f"{v:.2f}"

        q = qa["question"][:30] + ("..." if len(qa["question"]) > 30 else "")
        lines.append(
            f"| {qa['id']} | {qa['paper_name']} | {fmt(f)} | {fmt(c)} | {fmt(p)} | {fmt(r)} | {q} |"
        )

    report_path = REPORT_DIR / "evaluation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("报告已写入: %s", report_path)

    # ---- JSON 详细结果 ----
    json_data = {
        "timestamp": timestamp,
        "total": len(qa_pairs),
        "total_time_seconds": total_time,
        "metrics": {
            m: {
                "mean": stats[m]["mean"],
                "pass_count": stats[m]["pass"],
                "fail_count": stats[m]["fail"],
                "pass_rate": round(stats[m]["pass"] / stats[m]["total"] * 100, 1)
                if stats[m]["total"] > 0 else 0,
            }
            for m in metric_labels
        },
        "per_sample": [
            {
                "id": qa["id"],
                "paper": qa["paper_name"],
                "question": qa["question"],
                "scores": {
                    m: scores[m][idx]
                    for m in metric_labels
                },
            }
            for idx, qa in enumerate(qa_pairs)
        ],
    }

    results_path = REPORT_DIR / "evaluation_results.json"
    results_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("详细结果已写入: %s", results_path)

    # ---- 打印摘要 ----
    print("\n" + "=" * 65)
    print("RAGAS 评估结果摘要")
    print("=" * 65)
    for m, label in metric_labels.items():
        s = stats[m]
        pass_rate = s["pass"] / s["total"] * 100 if s["total"] > 0 else 0
        print(
            f"  {label:<30} {s['mean']:.3f}  ({s['pass']}/{s['total']} = {pass_rate:.1f}%)"
        )
    print(f"  耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    print("=" * 65)


# ---------------------------------------------------------------------------
# 6. 主流程
# ---------------------------------------------------------------------------

async def run_evaluation(*, max_workers=3, timeout=120, no_cache=False):
    """执行完整 RAGAS 评估流程。"""
    t0 = datetime.now()
    logger.info("=" * 60)
    logger.info("RAG 系统 RAGAS 专业评估（max_workers=%d, timeout=%ds）", max_workers, timeout)
    logger.info("=" * 60)

    # 1. 解析 QA 对
    qa_pairs = parse_qa_file(QA_FILE)
    logger.info("共 %d 个 QA 对", len(qa_pairs))

    # 2. 检查 RAG 结果缓存（前置避免 Qdrant 依赖）
    RAG_CACHE = REPORT_DIR / "rag_results.json"
    samples_data = []
    if no_cache:
        logger.info("--no-cache 指定，忽略 RAG 缓存")
    elif RAG_CACHE.exists():
        cached = json.loads(RAG_CACHE.read_text(encoding="utf-8"))
        if len(cached) == len(qa_pairs):
            logger.info("发现 RAG 结果缓存（%d 条），跳过 RAG 管线和 Qdrant 初始化", len(cached))
            samples_data = cached
        else:
            logger.info("缓存不完整（%d/%d），重新运行 RAG", len(cached), len(qa_pairs))

    # 3. 无缓存时：确保知识库就绪 + 运行 RAG 管线
    if not samples_data:
        logger.info("检查/创建测试知识库...")
        actual_kb_id = await ensure_kb_ready(TEST_KB_ID)
        if not actual_kb_id:
            logger.error("知识库准备失败，终止评估")
            return
        logger.info("使用知识库: %s", actual_kb_id)
        logger.info("开始运行 RAG 管线（共 %d 个问题）...", len(qa_pairs))
        for i, qa in enumerate(qa_pairs, 1):
            logger.info("[%d/%d] %s", i, len(qa_pairs), qa["id"])

            try:
                rag_result = await _retry(
                    lambda q=qa["question"]: rag_invoke(q, actual_kb_id)
                )
            except Exception:
                logger.exception("RAG 管线异常: %s", qa["id"])
                rag_result = {"answer": "", "retrieved_docs": []}

            retrieved_texts = [
                d["text"] for d in rag_result.get("retrieved_docs", [])
            ]

            samples_data.append({
                "user_input": qa["question"],
                "response": rag_result.get("answer", ""),
                "retrieved_contexts": retrieved_texts,
                "reference": qa["answer"],
            })

        # 保存缓存
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        RAG_CACHE.write_text(
            json.dumps(samples_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("RAG 结果已缓存到: %s", RAG_CACHE)

    # 4. 构建 RAGAS 数据集
    logger.info("构建 RAGAS EvaluationDataset...")
    from ragas import SingleTurnSample, EvaluationDataset

    samples = [
        SingleTurnSample(
            user_input=s["user_input"],
            retrieved_contexts=s["retrieved_contexts"],
            response=s["response"],
            reference=s["reference"],
        )
        for s in samples_data
    ]
    dataset = EvaluationDataset(samples=samples)

    # 5. RAGAS 评估
    eval_result = await run_ragas_evaluation(dataset, max_workers=max_workers, timeout=timeout)

    t1 = datetime.now()
    total_time = (t1 - t0).total_seconds()

    # 6. 生成报告
    generate_report(eval_result, qa_pairs, total_time)
    logger.info("评估完成！耗时 %.1f 分钟", total_time / 60)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAGAS 专业评估")
    parser.add_argument("--max-workers", type=int, default=3,
                        help="并发评分任务数（默认 3）")
    parser.add_argument("--timeout", type=int, default=120,
                        help="每次 LLM 调用超时秒数（默认 120）")
    parser.add_argument("--no-cache", action="store_true",
                        help="忽略 RAG 结果缓存，重新运行 RAG 管线")
    args = parser.parse_args()
    asyncio.run(run_evaluation(
        max_workers=args.max_workers,
        timeout=args.timeout,
        no_cache=args.no_cache,
    ))
