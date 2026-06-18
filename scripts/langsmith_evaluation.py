"""
RAG 系统 LangSmith 评估脚本

优势（相比 RAGAS）：
- 评估结果可视化：所有实验结果可在 LangSmith Dashboard 查看和对比
- 自定义评估器：支持 LLM-as-Judge 模式，评估更灵活
- 并行评估：LangSmith 自动处理并发，无需手动控制
- 实验追踪：每次评估自动记录为 experiment，方便 A/B 测试

评估维度：
- Faithfulness（有据性）：生成答案 vs 检索文档
- Answer Correctness（正确性）：生成答案 vs 标准答案
- Context Relevance（检索相关性）：检索文档 vs 问题

使用方式：
    # 1. 设置环境变量（在 backend/.env）
    LANGCHAIN_API_KEY=lsv2_pt_xxx
    LANGCHAIN_TRACING_V2=true

    # 2. 生成数据集（运行 RAG 管道 + 上传到 LangSmith）
    cd backend && PYTHONPATH=. python ../scripts/langsmith_evaluation.py --generate-dataset

    # 3. 运行评估
    cd backend && PYTHONPATH=. python ../scripts/langsmith_evaluation.py

    # 4. 指定样本数
    cd backend && PYTHONPATH=. python ../scripts/langsmith_evaluation.py --sample-size 10

    # 5. 仅评估特定指标
    cd backend && PYTHONPATH=. python ../scripts/langsmith_evaluation.py --metrics faithfulness,answer_correctness
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
logger = logging.getLogger("langsmith-eval")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

PDF_DIR = Path(__file__).resolve().parent.parent / "pdf"
QA_FILE = Path(__file__).resolve().parent.parent / "test_QA.md"
REPORT_DIR = Path(__file__).resolve().parent.parent / "evaluation_results"
TEST_KB_ID = "eval0000000001"
DATASET_NAME = "personalKD-RAG-Evaluation"

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
# 1. 解析 test_QA.md
# ---------------------------------------------------------------------------

def parse_qa_file(file_path: Path) -> list[dict]:
    """解析 test_QA.md，提取 QA 对及其来源论文。"""
    content = file_path.read_text(encoding="utf-8")
    qa_pairs = []

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
        matched = False
        for pname in paper_names:
            if pname in section[:50]:
                matched = True
                break
        if not matched:
            continue

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

async def create_new_kb() -> str | None:
    """创建新知识库并上传 PDF。"""
    from app.retrieval import dense, sparse
    from app.persistence.kb_repo import KbRepository
    from app.persistence.database import set_db_path, init_db

    set_db_path(str(BACKEND_DIR / "data" / "agent.db"))
    await init_db()

    logger.info("创建新知识库...")
    kb = await KbRepository.create(name="LangSmith Evaluation KB")
    aid = kb["id"]
    await dense.create_collection(aid)
    sparse.create_index(aid)
    logger.info("新知识库 ID: %s", aid)

    ok = await _upload_pdfs(aid)
    return aid if ok else None


async def ensure_kb_ready(kb_id: str, *, rebuild: bool = False) -> str | None:
    """检查/创建知识库，返回实际的 KB ID。

    Args:
        rebuild: 如果为 True，强制创建新知识库
    """
    from app.retrieval import dense
    from app.persistence.kb_repo import KbRepository
    from app.persistence.database import set_db_path, init_db

    set_db_path(str(BACKEND_DIR / "data" / "agent.db"))
    await init_db()

    # 强制重建
    if rebuild:
        logger.info("强制创建新知识库...")
        return await create_new_kb()

    # 尝试复用现有知识库
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
    return await create_new_kb()


async def _upload_pdfs(kb_id: str) -> bool:
    """上传 PDF 到知识库。"""
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

    logger.info("上传完成: %d 个文档块已存入 Qdrant + BM25", len(all_chunks))
    return True


# ---------------------------------------------------------------------------
# 3. RAG 管道
# ---------------------------------------------------------------------------

async def _retry(coro_factory, max_retries=3, base_delay=2.0):
    """指数退避重试。"""
    import random
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                delay = base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning("429 限流，%.1fs 后重试 (%d/%d)", delay, attempt + 1, max_retries)
                await asyncio.sleep(delay)
            else:
                raise


async def rag_invoke(question: str, kb_id: str) -> dict:
    """对单个问题执行完整 RAG 管线。"""
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
# 4. 生成 LangSmith 数据集
# ---------------------------------------------------------------------------

async def generate_dataset(qa_pairs: list[dict], kb_id: str, *, no_cache: bool = False) -> list[dict]:
    """运行 RAG 管道，生成 LangSmith 格式的数据集。

    返回格式：
    [
        {
            "inputs": {"question": "..."},
            "outputs": {
                "answer": "...",           # RAG 生成的答案
                "reference": "...",         # 标准答案
                "contexts": ["...", "..."], # 检索到的文档
                "paper_name": "...",        # 来源论文
            }
        },
        ...
    ]
    """
    RAG_CACHE = REPORT_DIR / "langsmith_rag_cache.json"

    # 检查缓存
    if not no_cache and RAG_CACHE.exists():
        cached = json.loads(RAG_CACHE.read_text(encoding="utf-8"))
        if len(cached) == len(qa_pairs):
            logger.info("已有完整 RAG 缓存（%d 条），直接使用", len(cached))
            return cached

    logger.info("开始运行 RAG 管道（共 %d 个问题）...", len(qa_pairs))
    dataset = []
    success_count = 0

    for i, qa in enumerate(qa_pairs, 1):
        logger.info("[%d/%d] %s: %s", i, len(qa_pairs), qa["id"], qa["question"][:50])
        try:
            rag_result = await _retry(
                lambda q=qa["question"]: rag_invoke(q, kb_id)
            )
            if rag_result.get("answer"):
                success_count += 1
        except Exception:
            logger.exception("RAG 管道异常: %s", qa["id"])
            rag_result = {"answer": "", "retrieved_docs": []}

        # 提取检索文档文本
        contexts = [doc["text"] for doc in rag_result.get("retrieved_docs", [])]

        # LangSmith 数据集格式
        dataset.append({
            "inputs": {"question": qa["question"]},
            "outputs": {
                "answer": rag_result.get("answer", ""),
                "reference": qa["answer"],
                "contexts": contexts,
                "paper_name": qa["paper_name"],
                "paper_pdf": qa["paper_pdf"],
            },
        })

    # 保存缓存
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    RAG_CACHE.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "RAG 管道完成: %d/%d 成功, 缓存: %s",
        success_count, len(qa_pairs), RAG_CACHE,
    )

    return dataset


# ---------------------------------------------------------------------------
# 5. LangSmith 数据集管理
# ---------------------------------------------------------------------------

def upload_to_langsmith(dataset: list[dict]):
    """上传数据集到 LangSmith。"""
    from langsmith import Client

    client = Client()

    # 检查数据集是否已存在
    try:
        existing = client.read_dataset(dataset_name=DATASET_NAME)
        logger.info("数据集 '%s' 已存在 (id=%s)，将删除并重建", DATASET_NAME, existing.id)
        client.delete_dataset(dataset_id=existing.id)
    except Exception:
        logger.info("创建新数据集: %s", DATASET_NAME)

    # 创建数据集
    dataset_obj = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="personalKD RAG 系统评估数据集，包含 25 个 QA 对",
    )

    # 批量上传示例
    inputs = [item["inputs"] for item in dataset]
    outputs = [item["outputs"] for item in dataset]

    client.create_examples(
        inputs=inputs,
        outputs=outputs,
        dataset_id=dataset_obj.id,
    )

    logger.info("数据集上传完成: %s (id=%s, %d 条)", DATASET_NAME, dataset_obj.id, len(dataset))
    return dataset_obj.id


# ---------------------------------------------------------------------------
# 6. LangSmith 评估器
# ---------------------------------------------------------------------------

def get_llm_judge():
    """获取 LLM Judge（使用 DashScope qwen-flash）。"""
    from langchain_openai import ChatOpenAI

    ds_base = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    ds_model = os.environ.get("DASHSCOPE_MODEL", "qwen-flash")
    ds_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("dashscope_api_key", "")

    if not ds_key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY，请在 backend/.env 中添加")

    saved = {k: os.environ.pop(k) for k in _PROXY_KEYS if k in os.environ}
    try:
        return ChatOpenAI(
            model=ds_model,
            api_key=ds_key,
            base_url=ds_base,
            temperature=0,
            max_tokens=1024,
            request_timeout=60,
        )
    finally:
        os.environ.update(saved)


def create_faithfulness_evaluator():
    """创建有据性评估器：检查答案是否基于检索文档。"""
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field

    class GradeFaithfulness(BaseModel):
        """有据性评分。"""
        score: int = Field(description="0-10 分，10 表示完全基于文档")
        reasoning: str = Field(description="评分理由")

    def faithfulness_evaluator(run, example) -> dict:
        """评估答案的有据性。"""
        try:
            prediction = run.outputs.get("answer", "")
            contexts = run.outputs.get("contexts", [])

            if not prediction or not contexts:
                return {"key": "faithfulness", "score": 0, "comment": "缺少答案或上下文"}

            context_text = "\n\n".join(contexts[:5])

            llm = get_llm_judge()
            structured_llm = llm.with_structured_output(GradeFaithfulness)

            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个严格的评估专家。请评估"回答"是否基于提供的"参考文档"。

评分标准：
- 10分：回答完全基于文档，没有添加任何文档中没有的信息
- 8-9分：回答主要基于文档，有少量合理推断
- 6-7分：回答部分基于文档，但有一些文档中没有的信息
- 4-5分：回答只有少部分基于文档，大部分是自行补充的
- 2-3分：回答几乎不基于文档，主要是幻觉
- 0-1分：回答完全不基于文档，或与文档矛盾"""),
                ("human", "参考文档：\n{context}\n\n回答：\n{answer}"),
            ])

            grader = prompt | structured_llm
            result = grader.invoke({"context": context_text, "answer": prediction})

            return {
                "key": "faithfulness",
                "score": result.score / 10,
                "comment": result.reasoning,
            }
        except Exception as e:
            logger.warning("有据性评估失败: %s", e)
            return {"key": "faithfulness", "score": None, "comment": str(e)}

    return faithfulness_evaluator


def create_answer_correctness_evaluator():
    """创建正确性评估器：比较生成答案与标准答案。"""
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field

    class GradeCorrectness(BaseModel):
        """正确性评分。"""
        score: int = Field(description="0-10 分，10 表示与标准答案完全一致")
        reasoning: str = Field(description="评分理由")

    def answer_correctness_evaluator(run, example) -> dict:
        """评估答案的正确性。"""
        try:
            prediction = run.outputs.get("answer", "")
            reference = example.outputs.get("reference", "")

            if not prediction or not reference:
                return {"key": "answer_correctness", "score": 0, "comment": "缺少答案或参考答案"}

            llm = get_llm_judge()
            structured_llm = llm.with_structured_output(GradeCorrectness)

            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个严格的评估专家。请比较"学生答案"和"标准答案"的一致程度。

评分标准：
- 10分：学生答案与标准答案在语义上完全一致，即使表述不同
- 8-9分：学生答案包含了标准答案的核心信息，有少量遗漏或多余
- 6-7分：学生答案包含了标准答案的大部分信息，但有一些错误或遗漏
- 4-5分：学生答案只包含了标准答案的一半左右信息
- 2-3分：学生答案只包含了标准答案的少量信息
- 0-1分：学生答案与标准答案完全不相关或矛盾"""),
                ("human", "标准答案：\n{reference}\n\n学生答案：\n{prediction}"),
            ])

            grader = prompt | structured_llm
            result = grader.invoke({"reference": reference, "prediction": prediction})

            return {
                "key": "answer_correctness",
                "score": result.score / 10,
                "comment": result.reasoning,
            }
        except Exception as e:
            logger.warning("正确性评估失败: %s", e)
            return {"key": "answer_correctness", "score": None, "comment": str(e)}

    return answer_correctness_evaluator


def create_context_relevance_evaluator():
    """创建检索相关性评估器：检查检索文档是否与问题相关。"""
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field

    class GradeRelevance(BaseModel):
        """相关性评分。"""
        score: int = Field(description="0-10 分，10 表示检索文档与问题高度相关")
        reasoning: str = Field(description="评分理由")

    def context_relevance_evaluator(run, example) -> dict:
        """评估检索文档的相关性。"""
        try:
            question = example.inputs.get("question", "")
            contexts = run.outputs.get("contexts", [])

            if not question or not contexts:
                return {"key": "context_relevance", "score": 0, "comment": "缺少问题或上下文"}

            context_text = "\n\n".join(contexts[:5])

            llm = get_llm_judge()
            structured_llm = llm.with_structured_output(GradeRelevance)

            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个严格的评估专家。请评估"检索文档"与"用户问题"的相关程度。

评分标准：
- 10分：检索文档完全包含回答问题所需的信息
- 8-9分：检索文档包含了回答问题所需的大部分信息
- 6-7分：检索文档包含了回答问题所需的部分信息
- 4-5分：检索文档只包含了少量与问题相关的信息
- 2-3分：检索文档几乎没有与问题相关的信息
- 0-1分：检索文档与问题完全不相关"""),
                ("human", "用户问题：\n{question}\n\n检索文档：\n{context}"),
            ])

            grader = prompt | structured_llm
            result = grader.invoke({"question": question, "context": context_text})

            return {
                "key": "context_relevance",
                "score": result.score / 10,
                "comment": result.reasoning,
            }
        except Exception as e:
            logger.warning("相关性评估失败: %s", e)
            return {"key": "context_relevance", "score": None, "comment": str(e)}

    return context_relevance_evaluator


# ---------------------------------------------------------------------------
# 7. LangSmith 评估
# ---------------------------------------------------------------------------

def create_rag_predictor_from_cache(cache_file: Path):
    """从缓存创建 RAG 预测函数。"""
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    cache_map = {item["inputs"]["question"]: item["outputs"] for item in cache}

    def predict(inputs: dict) -> dict:
        """从缓存读取 RAG 结果。"""
        question = inputs["question"]
        if question in cache_map:
            return cache_map[question]
        return {"answer": "", "contexts": []}

    return predict


async def run_langsmith_evaluation(
    *,
    metrics: list[str] | None = None,
    experiment_prefix: str = "rag-eval",
):
    """运行 LangSmith 评估。"""
    from langsmith import Client
    from langsmith.evaluation import evaluate

    client = Client()

    # 检查数据集是否存在
    try:
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        logger.info("使用数据集: %s (id=%s)", DATASET_NAME, dataset.id)
    except Exception:
        logger.error("数据集 '%s' 不存在，请先运行 --generate-dataset", DATASET_NAME)
        return

    # 准备评估器
    all_evaluators = {
        "faithfulness": create_faithfulness_evaluator(),
        "answer_correctness": create_answer_correctness_evaluator(),
        "context_relevance": create_context_relevance_evaluator(),
    }

    if metrics:
        evaluators = [all_evaluators[m] for m in metrics if m in all_evaluators]
    else:
        evaluators = list(all_evaluators.values())

    logger.info("评估指标: %d 个", len(evaluators))

    # 使用缓存的预测函数（避免重复运行 RAG）
    RAG_CACHE = REPORT_DIR / "langsmith_rag_cache.json"
    if RAG_CACHE.exists():
        predict_fn = create_rag_predictor_from_cache(RAG_CACHE)
        logger.info("使用 RAG 缓存进行评估")
    else:
        logger.error("未找到 RAG 缓存，请先运行 --generate-dataset")
        return

    # 运行评估
    logger.info("开始 LangSmith 评估...")
    t0 = datetime.now()

    experiment_results = evaluate(
        predict_fn,
        data=DATASET_NAME,
        evaluators=evaluators,
        experiment_prefix=experiment_prefix,
        metadata={
            "evaluation_time": datetime.now().isoformat(),
            "metrics": metrics or ["all"],
        },
    )

    elapsed = (datetime.now() - t0).total_seconds()
    logger.info("评估完成！耗时 %.1f 分钟", elapsed / 60)

    # 打印结果链接
    print("\n" + "=" * 65)
    print("LangSmith 评估完成！")
    print("=" * 65)
    print(f"  实验前缀: {experiment_prefix}")
    print(f"  数据集: {DATASET_NAME}")
    print(f"  耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"\n  请访问 LangSmith Dashboard 查看详细结果:")
    print(f"  https://smith.langchain.com")
    print("=" * 65)

    return experiment_results


# ---------------------------------------------------------------------------
# 8. 本地报告生成
# ---------------------------------------------------------------------------

def generate_local_report(experiment_results, qa_pairs: list[dict], total_time: float):
    """生成本地评估报告（Markdown + JSON）。"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 从 experiment_results 提取分数
    scores = {
        "faithfulness": [],
        "answer_correctness": [],
        "context_relevance": [],
    }

    # 检查 experiment_results 是否有效
    if not experiment_results:
        logger.warning("experiment_results 为空，跳过报告生成")
        return

    # experiment_results 是 ExperimentResults 对象，可迭代
    # 每个元素是 ExperimentResultRow: {run, example, evaluation_results}
    for run_result in experiment_results:
        eval_results = run_result.get("evaluation_results", {})
        for eval_result in eval_results.get("results", []):
            key = eval_result.key
            score = eval_result.score
            if key in scores and score is not None:
                scores[key].append(score)

    # 统计
    stats = {}
    for metric_name, values in scores.items():
        valid = [v for v in values if v is not None and not (isinstance(v, float) and v != v)]
        stats[metric_name] = {
            "mean": round(sum(valid) / len(valid), 4) if valid else 0,
            "pass": sum(1 for v in valid if v >= 0.9),
            "fail": sum(1 for v in valid if v < 0.9),
            "total": len(valid),
        }

    ALL_METRIC_META = {
        "faithfulness": {"label": "Faithfulness（有据性）", "meaning": "生成答案是否忠于检索文档"},
        "answer_correctness": {"label": "AnswerCorrectness（正确性）", "meaning": "生成答案与标准答案的一致程度"},
        "context_relevance": {"label": "ContextRelevance（检索相关性）", "meaning": "检索到的文档是否与问题相关"},
    }

    lines = [
        "# RAG 系统评估报告（LangSmith）",
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

    for m, meta in ALL_METRIC_META.items():
        s = stats[m]
        pass_rate = s["pass"] / s["total"] * 100 if s["total"] > 0 else 0
        status = "PASS" if pass_rate >= 90 else "WARN" if pass_rate >= 70 else "FAIL"
        lines.append(f"| {meta['label']} | {s['mean']:.3f} | {s['pass']}/{s['total']} ({pass_rate:.0f}%) {status} | {meta['meaning']} |")

    report_path = REPORT_DIR / "langsmith_evaluation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("报告已写入: %s", report_path)

    # 打印摘要
    print("\n" + "=" * 65)
    print("LangSmith 评估结果摘要")
    print("=" * 65)
    for m, meta in ALL_METRIC_META.items():
        s = stats[m]
        pass_rate = s["pass"] / s["total"] * 100 if s["total"] > 0 else 0
        print(f"  {meta['label']:<30} {s['mean']:.3f}  ({s['pass']}/{s['total']} = {pass_rate:.1f}%)")
    print(f"  耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    print("=" * 65)


# ---------------------------------------------------------------------------
# 9. 主流程
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="LangSmith RAG 评估")
    parser.add_argument("--generate-dataset", action="store_true",
                        help="运行 RAG 管道并上传数据集到 LangSmith")
    parser.add_argument("--rebuild-kb", action="store_true",
                        help="强制创建新知识库（不复用现有）")
    parser.add_argument("--metrics", type=str, default=None,
                        help="评估指标（逗号分隔）: faithfulness,answer_correctness,context_relevance")
    parser.add_argument("--experiment-prefix", type=str, default="rag-eval",
                        help="实验前缀（用于区分不同评估）")
    parser.add_argument("--no-cache", action="store_true",
                        help="忽略缓存，重新运行 RAG 管道")
    args = parser.parse_args()

    # 解析指标列表
    metrics = None
    if args.metrics:
        metrics = [m.strip() for m in args.metrics.split(",")]

    # 解析 QA 对
    qa_pairs = parse_qa_file(QA_FILE)
    logger.info("共 %d 个 QA 对", len(qa_pairs))

    # 生成数据集
    if args.generate_dataset:
        # 生成数据集时默认创建新知识库
        logger.info("创建新知识库...")
        kb_id = await ensure_kb_ready(TEST_KB_ID, rebuild=True)
        if not kb_id:
            logger.error("知识库准备失败，终止")
            return

        # 运行 RAG 管道
        dataset = await generate_dataset(qa_pairs, kb_id, no_cache=args.no_cache)

        # 上传到 LangSmith
        upload_to_langsmith(dataset)

        print("\n" + "=" * 65)
        print("数据集生成完成！")
        print("=" * 65)
        print(f"  数据集名称: {DATASET_NAME}")
        print(f"  知识库 ID: {kb_id}")
        print(f"  样本数: {len(dataset)}")
        print(f"\n  下一步：运行评估")
        print(f"  cd backend && PYTHONPATH=. python ../scripts/langsmith_evaluation.py")
        print("=" * 65)
        return

    # 运行评估
    t0 = datetime.now()
    experiment_results = await run_langsmith_evaluation(
        metrics=metrics,
        experiment_prefix=args.experiment_prefix,
    )
    elapsed = (datetime.now() - t0).total_seconds()

    # 生成本地报告
    if experiment_results:
        generate_local_report(experiment_results, qa_pairs, elapsed)

    logger.info("评估完成！耗时 %.1f 分钟", elapsed / 60)


if __name__ == "__main__":
    asyncio.run(main())
