from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from pathlib import Path

import torch

from app.config import settings

_model = None
_device = None
_model_init_lock = threading.Lock()

# 专用线程池：PyTorch 推理已释放 GIL，1 个 worker 足够避免 GPU 内存争抢
_reranker_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

MODELSCOPE_REPO = "jinaai/jina-reranker-v3"


def _get_device() -> str:
    global _device
    if _device is None:
        _device = "cuda" if torch.cuda.is_available() else "cpu"
    return _device


def _ensure_model_downloaded(model_path: Path) -> None:
    """Download model from ModelScope if not exists locally."""
    if (model_path / "model.safetensors").exists():
        return

    import logging

    logger = logging.getLogger(__name__)
    logger.info("模型文件不存在，从 ModelScope 下载: %s", MODELSCOPE_REPO)

    try:
        from modelscope import snapshot_download

        model_path.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            MODELSCOPE_REPO,
            local_dir=str(model_path),
        )
        logger.info("模型下载完成: %s", model_path)
    except ImportError:
        logger.error(
            "modelscope 未安装，请运行: pip install modelscope\n"
            "或手动下载模型: modelscope download --model %s --local_dir %s",
            MODELSCOPE_REPO,
            model_path,
        )
        raise
    except Exception:
        logger.exception("从 ModelScope 下载模型失败")
        raise


def get_model():
    global _model
    if _model is None:
        with _model_init_lock:
            # Double-check after acquiring lock
            if _model is not None:
                return _model

            import logging

            from transformers import AutoModel

            logger = logging.getLogger(__name__)
            model_path = Path(settings.reranker_model_path)

            _ensure_model_downloaded(model_path)

            logger.info("Loading Jina Reranker v3 from %s", model_path)
            try:
                _model = AutoModel.from_pretrained(
                    str(model_path),
                    dtype=torch.float16 if _get_device() == "cuda" else "auto",
                    device_map=_get_device(),
                    trust_remote_code=True,
                )
                _model.eval()
                logger.info("Reranker loaded on %s", _get_device())
            except Exception:
                logger.exception("Reranker 加载失败，将跳过重排序")
                _model = None
    return _model


async def rerank(
    query: str,
    documents: list[dict],
    top_n: int = 5,
) -> list[dict]:
    """Re-rank documents using Jina Reranker v3."""
    if not documents:
        return []

    model = get_model()
    if model is None:
        import logging

        logging.getLogger(__name__).warning("Reranker 不可用，跳过重排序")
        return documents[:top_n]

    texts = [doc["text"] for doc in documents]
    loop = asyncio.get_event_loop()

    def _run_rerank():
        results = model.rerank(query, texts, top_n=top_n)
        return results

    try:
        reranked = await loop.run_in_executor(_reranker_executor, _run_rerank)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Reranker failed: %s, falling back to input order", e)
        return documents[:top_n]

    # Map back to original document data
    result = []
    for item in reranked:
        idx = item.get("index")
        if idx is not None and idx < len(documents):
            doc = dict(documents[idx])
            doc["rerank_score"] = float(item.get("relevance_score", 0.0))
            doc["score"] = doc.get("rerank_score", doc.get("score", 0.0))
            result.append(doc)

    return result
