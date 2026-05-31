from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, conversation, document, knowledge_base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Knowledge Base Agent",
    description="Personal knowledge base Q&A system with LangGraph",
    version="0.1.0",
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
