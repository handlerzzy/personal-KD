from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import close_checkpointer, init_checkpointer
from app.api import chat, conversation, document, knowledge_base
from app.persistence.database import close_db, init_db, set_db_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and checkpointer on startup, close on shutdown."""
    # Startup
    set_db_path("data/agent.db")
    await init_db()
    await init_checkpointer("data/agent.db")
    logger.info("Application started: database and checkpointer initialized")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge_base.router, prefix="/api")
app.include_router(document.router, prefix="/api")
app.include_router(conversation.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
