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
    cd backend && PYTHONPATH=. python ../scripts/rag_evaluation.py --max-workers 14 --timeout 600
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

async def rebuild_kb(kb_id: str) -> str | None:
    """删除旧 KB 数据，用新 chunker 重新创建。"""
    from app.retrieval import dense, sparse
    from app.persistence.kb_repo import KbRepository
    from app.persistence.database import set_db_path, init_db

    set_db_path(str(BACKEND_DIR / "data" / "agent.db"))
    await init_db()

    logger.info("重建知识库（删除旧数据 + 新 chunker）...")

    # 删除旧 Qdrant collection
    try:
        client = dense.get_client()
        col_name = f"kb_{kb_id}"
        if await client.collection_exists(col_name):
            await client.delete_collection(col_name)
            logger.info("已删除旧 Qdrant 集合: %s", col_name)
    except Exception:
        logger.warning("删除 Qdrant 集合失败（可能不存在）")

    # 删除旧 BM25 索引
    sparse.delete_index(kb_id)
    logger.info("已删除旧 BM25 索引: %s", kb_id)

    # 删除旧 SQLite KB 记录
    try:
        await KbRepository.delete(kb_id)
    except Exception:
        pass

    # 重新创建
    await dense.create_collection(kb_id)
    sparse.create_index(kb_id)
    # 直接插入 SQLite，保留指定的 kb_id
    from app.persistence.database import get_db
    from datetime import UTC, datetime
    db = await get_db()
    now = datetime.now(UTC).isoformat()
    await db.execute(
        "INSERT OR REPLACE INTO knowledge_bases (id, name, description, created_at) VALUES (?, ?, ?, ?)",
        (kb_id, "RAGAS Evaluation KB", "", now),
    )
    await db.commit()

    # 用新 chunker 上传 PDF
    ok = await _upload_pdfs(kb_id)
    if ok:
        logger.info("知识库重建完成")
    return kb_id if ok else None


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
    all_chunk_ids = [c["chunk_id"] for c in all_chunks]
    sparse.add_documents(kb_id, all_texts, chunk_ids=all_chunk_ids)

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

    # Use retrieved_docs directly (reranker already filters/scores)
    return {
        "answer": result.get("answer", ""),
        "retrieved_docs": result.get("retrieved_docs", []),
    }


# ---------------------------------------------------------------------------
# 4. RAGAS 评估
# ---------------------------------------------------------------------------

def get_ragas_llm(timeout: int = 180, max_tokens: int = 4096):
    """创建 RAGAS 评估用 LLM（使用 DashScope qwen-flash，通过 OpenAI 兼容接口调用）。

    直接创建 LangChain ChatOpenAI 而不是通过 ``llm_factory``，以便显式设置
    ``max_tokens`` —— RAGAS 评估不需要太大的 token 预算，4096 已经足够。
    过大的 max_tokens 会导致模型生成过长的输出，显著增加响应时间。

    ``timeout`` 传递给 OpenAI client 的 ``request_timeout``，防止 API 响应
    过慢时挂起。
    """
    from langchain_openai import ChatOpenAI

    # 使用 DashScope（阿里云）的 qwen-flash 模型
    # .env 中可能是小写 dashscope_api_key（pydantic 风格），也可能是大写
    ds_base = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    ds_model = os.environ.get("DASHSCOPE_MODEL", "qwen-flash")
    ds_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("dashscope_api_key", "")

    if not ds_key:
        raise RuntimeError(
            "缺少 DASHSCOPE_API_KEY，请在 backend/.env 中添加：\n"
            "  DASHSCOPE_API_KEY=sk-xxxxxxxx\n"
            "可在 https://dashscope.console.aliyun.com/ 获取"
        )

    saved = {k: os.environ.pop(k) for k in _PROXY_KEYS if k in os.environ}
    try:
        logger.info("RAGAS 评估 LLM: %s (%s), timeout=%ds, max_tokens=%d", ds_model, ds_base, timeout, max_tokens)
        return ChatOpenAI(
            model=ds_model,
            api_key=ds_key,
            base_url=ds_base,
            temperature=0,
            max_tokens=max_tokens,
            request_timeout=timeout,
        )
    finally:
        os.environ.update(saved)


def get_ragas_embeddings():
    """创建 RAGAS 评估用的 Embeddings（使用智谱 embedding-3，通过 OpenAI 兼容接口调用）。"""
    from langchain_openai import OpenAIEmbeddings
    from ragas.embeddings.base import LangchainEmbeddingsWrapper

    # 使用智谱的 embedding-3 模型
    ds_base = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    ds_model = os.environ.get("ZHIPU_MODEL", "embedding-3")
    ds_key = os.environ.get("ZHIPU_API_KEY") or os.environ.get("zhipu_api_key", "")

    saved = {k: os.environ.pop(k) for k in _PROXY_KEYS if k in os.environ}
    try:
        logger.info("RAGAS 评估 Embeddings: %s (%s)", ds_model, ds_base)
        lce = OpenAIEmbeddings(
            model=ds_model,
            openai_api_key=ds_key,
            openai_api_base=ds_base,
        )
        return LangchainEmbeddingsWrapper(embeddings=lce)
    finally:
        os.environ.update(saved)


async def run_ragas_evaluation(dataset, *, max_workers=16, timeout=600, metric_names=None, max_tokens=4096):
    """使用 RAGAS 评估数据集。支持单指标或多指标。"""
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_correctness,
        context_precision,
        context_recall,
    )
    from ragas.run_config import RunConfig

    # 指标映射
    METRIC_MAP = {
        "faithfulness": faithfulness,
        "answer_correctness": answer_correctness,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }

    # 选择指标
    if metric_names and metric_names != ["all"]:
        metrics = [METRIC_MAP[m] for m in metric_names if m in METRIC_MAP]
    else:
        metrics = list(METRIC_MAP.values())

    metric_labels = [m.name for m in metrics]
    logger.info("评估指标: %s", metric_labels)

    logger.info("初始化 RAGAS 评估 LLM...")
    llm = get_ragas_llm(timeout=timeout, max_tokens=max_tokens)
    embeddings = get_ragas_embeddings()

    # 降低并发度避免 API 限流，增加超时时间
    # DeepSeek API 对并发请求有限制，10 个并发容易触发限流
    effective_workers = min(max_workers, 5)  # 限制最大并发为 5
    effective_timeout = max(timeout, 600)    # 至少 600 秒超时

    run_config = RunConfig(
        max_workers=effective_workers,
        timeout=effective_timeout,
        max_retries=3,
        max_wait=30,  # 增加重试等待时间
        log_tenacity=False,
    )

    if max_workers > 5:
        logger.warning("并发数 %d 过高，已自动调整为 5 以避免 API 限流", max_workers)

    logger.info(
        "开始 RAGAS 评估（共 %d 个样本, %d 个指标, max_workers=%d, timeout=%ds, max_tokens=%d）...",
        len(dataset.samples), len(metrics), effective_workers, effective_timeout, max_tokens,
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

def generate_report(eval_result, qa_pairs: list[dict], total_time: float, report_suffix: str = ""):
    """生成评估报告（Markdown + JSON）。

    动态检测已评估的指标列，兼容单指标和多指标评估。
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    scores_df = eval_result.to_pandas()

    # ---- 动态检测已评估的指标列 ----
    ALL_METRIC_META = {
        "faithfulness": {
            "label": "Faithfulness（有据性）",
            "meaning": "生成答案是否忠于检索文档（无幻觉）",
        },
        "answer_correctness": {
            "label": "AnswerCorrectness（正确性）",
            "meaning": "生成答案与标准答案的一致程度",
        },
        "context_precision": {
            "label": "ContextPrecision（检索相关性）",
            "meaning": "检索到的文档是否与问题相关",
        },
        "context_recall": {
            "label": "ContextRecall（召回完整性）",
            "meaning": "标准答案的信息能否从检索文档中找到",
        },
    }

    # 只取 DataFrame 中实际存在的指标列
    available_metrics = [m for m in ALL_METRIC_META if m in scores_df.columns]
    if not available_metrics:
        logger.error("评估结果中没有找到任何指标列，可用列: %s", list(scores_df.columns))
        return

    scores = {m: scores_df[m].tolist() for m in available_metrics}

    logger.info("检测到 %d 个已评估指标: %s", len(available_metrics), available_metrics)

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
        "| 指标 | 平均分 | ≥0.9 通过率 | 含义 |",
        "|------|--------|------------|------|",
    ]

    for m in available_metrics:
        meta = ALL_METRIC_META[m]
        s = stats[m]
        pass_rate = s["pass"] / s["total"] * 100 if s["total"] > 0 else 0
        status = "PASS" if pass_rate >= 90 else "WARN" if pass_rate >= 70 else "FAIL"
        lines.append(
            f"| {meta['label']} | {s['mean']:.3f} | {s['pass']}/{s['total']} ({pass_rate:.0f}%) {status} | {meta['meaning']} |"
        )

    # 按论文分组
    lines.extend(["", "## 按论文分组统计", ""])
    paper_groups = {}
    for qa in qa_pairs:
        pname = qa["paper_name"]
        if pname not in paper_groups:
            paper_groups[pname] = []
        paper_groups[pname].append(qa)

    # 按论文分组表头（动态列）
    short_names = {
        "faithfulness": "Faith",
        "answer_correctness": "Correct",
        "context_precision": "Precision",
        "context_recall": "Recall",
    }
    header_cols = " | ".join(short_names.get(m, m[:6]) for m in available_metrics)
    sep_cols = " | ".join("---" for _ in available_metrics)
    lines.append(f"| 论文 | QA数 | {header_cols} |")
    lines.append(f"|------|------|{sep_cols}|")

    # Build per-paper stats
    for pname, group_qas in paper_groups.items():
        n = len(group_qas)
        indices = [idx for idx, qa in enumerate(qa_pairs) if qa["paper_name"] == pname]

        pstats = {}
        for m in available_metrics:
            vals = [scores[m][i] for i in indices]
            valid = [v for v in vals if v is not None and not (isinstance(v, float) and v != v)]
            pstats[m] = round(sum(valid) / len(valid), 3) if valid else 0

        stat_cols = " | ".join(f"{pstats[m]:.3f}" for m in available_metrics)
        lines.append(f"| {pname} | {n} | {stat_cols} |")

    # 失败案例分析
    lines.extend(["", "## 失败案例分析", ""])
    for m in available_metrics:
        meta = ALL_METRIC_META[m]
        failed = []
        for idx, val in enumerate(scores[m]):
            if val is not None and not (isinstance(val, float) and val != val) and val < 0.9:
                failed.append((idx, val, qa_pairs[idx]))

        if failed:
            lines.append(f"### {meta['label']}（{len(failed)} 个失败）")
            lines.append("")
            for idx, val, qa in failed[:10]:
                q = qa["question"][:60] + ("..." if len(qa["question"]) > 60 else "")
                lines.append(f"- **{qa['id']}** ({qa['paper_name']}): {q} → {val:.3f}")
            if len(failed) > 10:
                lines.append(f"- ... 还有 {len(failed) - 10} 个失败")
            lines.append("")

    # 逐题详情（动态列）
    lines.extend(["", "## 逐题详情", ""])
    detail_header = " | ".join(short_names.get(m, m[:5]) for m in available_metrics)
    detail_sep = " | ".join("---" for _ in available_metrics)
    lines.append(f"| ID | 论文 | {detail_header} | 问题（前30字） |")
    lines.append(f"|-----|------|{detail_sep}|----------------|")

    def _fmt(v):
        if v is None or (isinstance(v, float) and v != v):
            return "N/A"
        return f"{v:.2f}"

    for idx, qa in enumerate(qa_pairs):
        val_cols = " | ".join(_fmt(scores[m][idx]) for m in available_metrics)
        q = qa["question"][:30] + ("..." if len(qa["question"]) > 30 else "")
        lines.append(f"| {qa['id']} | {qa['paper_name']} | {val_cols} | {q} |")

    report_path = REPORT_DIR / f"evaluation_report{report_suffix}.md"
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
            for m in available_metrics
        },
        "per_sample": [
            {
                "id": qa["id"],
                "paper": qa["paper_name"],
                "question": qa["question"],
                "scores": {
                    m: scores[m][idx]
                    for m in available_metrics
                },
            }
            for idx, qa in enumerate(qa_pairs)
        ],
    }

    results_path = REPORT_DIR / f"evaluation_results{report_suffix}.json"
    results_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("详细结果已写入: %s", results_path)

    # ---- 打印摘要 ----
    print("\n" + "=" * 65)
    print("RAGAS 评估结果摘要")
    print("=" * 65)
    for m in available_metrics:
        meta = ALL_METRIC_META[m]
        s = stats[m]
        pass_rate = s["pass"] / s["total"] * 100 if s["total"] > 0 else 0
        print(
            f"  {meta['label']:<30} {s['mean']:.3f}  ({s['pass']}/{s['total']} = {pass_rate:.1f}%)"
        )
    print(f"  耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    print("=" * 65)


# ---------------------------------------------------------------------------
# 6. 主流程
# ---------------------------------------------------------------------------

async def run_pipeline_only(*, no_cache=False):
    """Stage 1: 仅运行 RAG Pipeline，缓存结果，不跑 RAGAS。"""
    t0 = datetime.now()
    logger.info("=" * 60)
    logger.info("Stage 1: RAG Pipeline 验证")
    logger.info("=" * 60)

    qa_pairs = parse_qa_file(QA_FILE)
    logger.info("共 %d 个 QA 对", len(qa_pairs))

    RAG_CACHE = REPORT_DIR / "rag_results.json"
    if not no_cache and RAG_CACHE.exists():
        cached = json.loads(RAG_CACHE.read_text(encoding="utf-8"))
        if len(cached) == len(qa_pairs):
            logger.info("已有完整 RAG 缓存（%d 条），跳过", len(cached))
            return

    logger.info("检查/创建测试知识库...")
    actual_kb_id = await ensure_kb_ready(TEST_KB_ID)
    if not actual_kb_id:
        logger.error("知识库准备失败，终止")
        return

    logger.info("开始运行 RAG 管线（共 %d 个问题）...", len(qa_pairs))
    samples_data = []
    success_count = 0

    for i, qa in enumerate(qa_pairs, 1):
        logger.info("[%d/%d] %s", i, len(qa_pairs), qa["id"])
        try:
            rag_result = await _retry(
                lambda q=qa["question"]: rag_invoke(q, actual_kb_id)
            )
            if rag_result.get("answer"):
                success_count += 1
        except Exception:
            logger.exception("RAG 管线异常: %s", qa["id"])
            rag_result = {"answer": "", "retrieved_docs": []}

        retrieved_texts = [d["text"] for d in rag_result.get("retrieved_docs", [])]
        samples_data.append({
            "user_input": qa["question"],
            "response": rag_result.get("answer", ""),
            "retrieved_contexts": retrieved_texts,
            "reference": qa["answer"],
        })

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    RAG_CACHE.write_text(
        json.dumps(samples_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    elapsed = (datetime.now() - t0).total_seconds()
    logger.info(
        "Stage 1 完成: %d/%d 成功, 耗时 %.1f 分钟, 缓存: %s",
        success_count, len(qa_pairs), elapsed / 60, RAG_CACHE,
    )


async def run_evaluation(
    *,
    max_workers=16,
    timeout=600,
    no_cache=False,
    metric_names=None,
    sample_size=None,
    max_tokens=4096,
):
    """Stage 2/3: 从缓存加载 RAG 结果，执行 RAGAS 评估。"""
    t0 = datetime.now()

    metric_label = ",".join(metric_names) if metric_names else "all"
    logger.info("=" * 60)
    logger.info("RAGAS 评估（指标=%s, 样本数=%s, max_workers=%d, max_tokens=%d）", metric_label, sample_size or "全部", max_workers, max_tokens)
    logger.info("=" * 60)

    # 1. 解析 QA 对
    qa_pairs = parse_qa_file(QA_FILE)
    logger.info("共 %d 个 QA 对", len(qa_pairs))

    # 2. 加载 RAG 结果缓存
    RAG_CACHE = REPORT_DIR / "rag_results.json"
    if not RAG_CACHE.exists():
        logger.error("未找到 RAG 缓存 (%s)，请先运行 Stage 1: --stage pipeline", RAG_CACHE)
        return

    samples_data = json.loads(RAG_CACHE.read_text(encoding="utf-8"))
    logger.info("加载 RAG 缓存: %d 条", len(samples_data))

    # 3. 采样（如果指定了 sample_size）
    if sample_size and sample_size < len(samples_data):
        import random
        random.seed(42)  # 可复现
        indices = sorted(random.sample(range(len(samples_data)), sample_size))
        samples_data = [samples_data[i] for i in indices]
        qa_pairs = [qa_pairs[i] for i in indices]
        logger.info("采样 %d 条", sample_size)

    # 4. 构建 RAGAS 数据集
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
    eval_result = await run_ragas_evaluation(
        dataset, max_workers=max_workers, timeout=timeout, metric_names=metric_names, max_tokens=max_tokens,
    )

    elapsed = (datetime.now() - t0).total_seconds()

    # 6. 生成报告（文件名含指标名）
    report_suffix = f"_{metric_label}" if metric_names and metric_names != ["all"] else ""
    generate_report(eval_result, qa_pairs, elapsed, report_suffix=report_suffix)
    logger.info("评估完成！耗时 %.1f 分钟", elapsed / 60)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAGAS 分阶段评估")
    parser.add_argument("--stage", choices=["pipeline", "eval"], default="eval",
                        help="pipeline=仅运行RAG管线, eval=运行RAGAS评估（默认 eval）")
    parser.add_argument("--rebuild-kb", action="store_true",
                        help="删除旧KB并用新chunker重建（在pipeline前执行）")
    parser.add_argument("--metric", type=str, default="all",
                        help="评估指标: faithfulness|answer_correctness|context_precision|context_recall|all（默认 all）")
    parser.add_argument("--sample-size", type=int, default=None,
                        help="评估样本数（默认全部）")
    parser.add_argument("--max-workers", type=int, default=5,
                        help="并发评分任务数（默认 5，过高会触发 API 限流）")
    parser.add_argument("--timeout", type=int, default=600,
                        help="每次 LLM 调用超时秒数（默认 600）")
    parser.add_argument("--max-tokens", type=int, default=4096,
                        help="LLM 最大输出 token 数（默认 4096，减少可加快响应速度）")
    parser.add_argument("--no-cache", action="store_true",
                        help="忽略 RAG 结果缓存，重新运行 RAG 管线")
    args = parser.parse_args()

    # 解析指标列表
    metric_names = None
    if args.metric != "all":
        metric_names = [m.strip() for m in args.metric.split(",")]

    async def _main():
        # Stage 0: 重建 KB
        if args.rebuild_kb:
            await rebuild_kb(TEST_KB_ID)

        if args.stage == "pipeline":
            # Stage 1: 仅运行 RAG Pipeline
            await run_pipeline_only(no_cache=args.no_cache)
        else:
            # Stage 2/3: RAGAS 评估
            await run_evaluation(
                max_workers=args.max_workers,
                timeout=args.timeout,
                no_cache=args.no_cache,
                metric_names=metric_names,
                sample_size=args.sample_size,
                max_tokens=args.max_tokens,
            )

    asyncio.run(_main())
