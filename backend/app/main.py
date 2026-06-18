from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent.graph import close_checkpointer, init_checkpointer
from app.api import auth, chat, conversation, document, knowledge_base
from app.persistence.database import close_db, init_db, set_db_path

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_root_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _root_level, logging.INFO),
    format=_LOG_FORMAT,
)

# Per-module overrides via env var: LOG_LEVELS="app.retrieval.dense=DEBUG,app.agent=WARNING"
for entry in os.environ.get("LOG_LEVELS", "").split(","):
    entry = entry.strip()
    if "=" in entry:
        module, level = entry.rsplit("=", 1)
        logging.getLogger(module.strip()).setLevel(
            getattr(logging, level.strip().upper(), logging.DEBUG)
        )

logger = logging.getLogger(__name__)


# ---------- Rate Limiting (in-memory, per-IP) ----------
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_AUTH = 10  # max requests per window for auth endpoints


def _check_rate_limit(ip: str, max_requests: int = _RATE_LIMIT_MAX_AUTH) -> bool:
    """Check if IP is within rate limit. Returns True if allowed."""
    now = time.time()
    # Remove expired entries
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[ip]) >= max_requests:
        return False
    _rate_limit_store[ip].append(now)
    return True


async def _warmup_llm():
    """Warm up LLM client to avoid cold start latency on first request."""
    from app.llm_cache import warmup_llm

    await warmup_llm()


def _warmup_reranker():
    """Pre-load Jina Reranker v3 into memory."""
    try:
        from app.retrieval.reranker import get_model

        get_model()
        logger.info("Reranker warmup completed")
    except Exception:
        logger.exception("Reranker warmup failed (non-fatal)")


def _warmup_jieba():
    """Pre-load jieba dictionary for BM25 tokenization."""
    try:
        import jieba

        jieba.initialize()
        logger.info("jieba warmup completed")
    except Exception:
        logger.exception("jieba warmup failed (non-fatal)")


async def _warmup_retrieval():
    """Warm up retrieval components (reranker + jieba) in background threads."""
    loop = asyncio.get_event_loop()
    await asyncio.gather(
        loop.run_in_executor(None, _warmup_reranker),
        loop.run_in_executor(None, _warmup_jieba),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and checkpointer on startup, close on shutdown."""
    # Startup
    set_db_path("data/agent.db")
    await init_db()
    await init_checkpointer("data/agent.db")
    logger.info("Application started: database and checkpointer initialized")

    # Warm up LLM and retrieval components in background (non-blocking)
    asyncio.create_task(_warmup_llm())
    asyncio.create_task(_warmup_retrieval())

    # Schedule periodic cleanup of expired blacklisted tokens (every 6 hours)
    async def _periodic_blacklist_cleanup():
        while True:
            await asyncio.sleep(6 * 3600)
            try:
                from app.persistence.user_repo import TokenBlacklistRepository

                deleted = await TokenBlacklistRepository.cleanup_expired()
                if deleted > 0:
                    logger.info("Blacklist cleanup: removed %d expired tokens", deleted)
            except Exception:
                logger.exception("Blacklist cleanup failed")

    asyncio.create_task(_periodic_blacklist_cleanup())

    yield
    # Shutdown
    await close_checkpointer()
    await close_db()
    logger.info("Application stopped: connections closed")


app = FastAPI(
    title="Knowledge Base Agent",
    description="Personal knowledge base Q&A system with LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------- CORS (configurable via env) ----------
# Production: set CORS_ORIGINS=http://your-domain.com in .env
# Development: defaults to * (when DEVELOPMENT=true)
_cors_origins_str = os.environ.get("CORS_ORIGINS", "")
if _cors_origins_str:
    _cors_origins = [o.strip() for o in _cors_origins_str.split(",") if o.strip()]
elif os.environ.get("DEVELOPMENT", "").lower() == "true":
    _cors_origins = ["*"]
else:
    # Production default: no cross-origin allowed (same-origin only)
    _cors_origins = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=bool(_cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Security Headers + Rate Limiting + Request Logging ----------
@app.middleware("http")
async def security_middleware(request: Request, call_next) -> Response:
    """Add security headers, rate limiting for auth endpoints, and request logging."""
    path = request.url.path

    # Rate limiting for auth endpoints (login/register)
    if path in ("/api/auth/login", "/api/auth/register"):
        client_ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(client_ip):
            logger.warning("Rate limit exceeded: ip=%s, path=%s", client_ip, path)
            return Response(
                content='{"detail":"请求过于频繁，请稍后再试"}',
                status_code=429,
                media_type="application/json",
            )

    # Request logging
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method,
        path,
        response.status_code,
        elapsed_ms,
    )

    # Security headers (skip for static assets)
    if not path.startswith("/assets"):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # CSP: allow inline styles/scripts for Vue SPA, connect to API
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "font-src 'self'"
        )

    return response


app.include_router(auth.router)
app.include_router(knowledge_base.router, prefix="/api")
app.include_router(document.router, prefix="/api")
app.include_router(conversation.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---------- 前端静态文件服务（Docker 部署时使用） ----------
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if _STATIC_DIR.is_dir():
    # 挂载静态资源目录（JS/CSS/图片等）
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """SPA 回退: 未匹配的路由统一返回 index.html，由前端路由接管。"""
        file_path = _STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_STATIC_DIR / "index.html")
