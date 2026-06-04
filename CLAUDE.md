# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


## User Requirements

1. The user requests that Claude Code uses the project's virtual environment at `/home/handler/文档/learning/projects/personalKD/.venv` in scenarios that require an execution environment, such as testing or running code.

2. The installed dependencies need to synchronize two files: `pyproject.toml` 
in the root directory and `requirements.txt` in the `/backend` subdirectory.

3. When using langsmith or other packages, you need to query their latest APIs through the `context7` plugin.


## Project Overview

Personal Knowledge Base Q&A system (kb-agent). Users upload documents (PDF/TXT/MD), the system indexes them, and answers questions via LLM with source citations.

**Stack:** FastAPI + LangGraph (backend) | Vue 3 + Vite (frontend) | Qdrant (vector DB) | ZhipuAI embeddings + mimo-v2.5 LLM via ChatOpenAI (langchain-openai)

@.claude/project-state.md

## Commands

```bash
# Setup
make venv                    # Create .venv with Python 3.12
make install-dev             # Install all deps (backend + dev tools)
cd frontend && npm install   # Frontend deps

# Run (two terminals)
make dev-backend             # uvicorn on :8000 (must run from backend/ dir for .env)
make dev-frontend            # Vite on :5173 (proxies /api → :8000)

# Qdrant
docker-compose up -d         # Starts Qdrant on :6333

# Lint & Test
make lint                    # ruff (backend) + eslint (frontend)
make format                  # ruff format
make test                    # pytest in backend/
```

**Backend .env** must be in `backend/` directory (pydantic-settings reads it from CWD). See `backend/env.example` for required vars: ZHIPU_API_KEY, LLM_API_BASE, LLM_API_KEY, LLM_MODEL, QDRANT_URL.

## Architecture

### Backend (`backend/app/`)

```
api/           → FastAPI route handlers (REST + SSE streaming)
agent/         → LangGraph StateGraph: retrieve → qa
  nodes/         retrieval_node (hybrid search), qa_node (ChatOpenAI via langchain-openai)
document/      → parser (PyMuPDF), chunker (LangChain 500 chars), embedder (ZhipuAI)
retrieval/     → dense (Qdrant), sparse (bm25x), hybrid (RRF fusion), reranker (Jina v3)
persistence/   → SQLite persistence layer (KB, conversations, messages) + LangGraph checkpointer
models/        → Pydantic models: KnowledgeBase, Document, Conversation, Message
```

**Q&A pipeline:** Query → Embed (ZhipuAI) → Dense+Sparse retrieval → RRF fusion → Rerank (Jina) → LLM streaming (mimo-v2.5 via ChatOpenAI). Uses `graph.astream(stream_mode=["updates","messages"])` for unified streaming — updates yield sources from retrieve node, messages yield token-level `AIMessageChunk` from qa node. Checkpointer (`AsyncSqliteSaver`) writes state on every invocation.

**Persistence:** SQLite database (`data/agent.db`) stores KB metadata, conversations, and messages. LangGraph `AsyncSqliteSaver` checkpointer manages agent state for conversation history. Document metadata and uploaded files remain file-based under `data/knowledge_bases/{kb_id}/`.

**Data isolation:** Each KB gets its own Qdrant collection (`kb_{id}`) + BM25 index directory. All metadata in SQLite with foreign key cascades.

**SSE streaming:** POST `/api/kb/{id}/conversations/{conv_id}/chat` returns event stream with types: `reasoning`, `answer`, `sources`, `done`. Frontend uses `fetch` + `ReadableStream` (not EventSource).

### Frontend (`frontend/src/`)

```
api/index.ts          → All REST + SSE streaming calls (native fetch)
composables/          → useKb, useConversation, useChat (state management, no Vuex/Pinia)
components/           → Sidebar, ChatView, MessageBubble, ThinkingBlock, ChatInput, KbModal, DocList, Toast
types/index.ts        → TypeScript interfaces
```

**State flow:** `App.vue` orchestrates composables → passes props/events to child components. SSE streaming accumulates tokens in real-time via `useChat` refs.

### Key Patterns

- **SQLite persistence:** KB metadata, conversations, and messages stored in `data/agent.db`. LangGraph `AsyncSqliteSaver` checkpointer for agent state.
- **File-based document storage:** Uploaded files and document metadata remain JSON under `data/knowledge_bases/{kb_id}/`.
- **Embedding batching:** ZhipuAI API limits 64 texts/request; `embed_texts()` batches automatically.
- **Reranker graceful fallback:** If Jina model fails to load, reranking is skipped (returns top-N from fusion).
- **Logging:** All `try/except` blocks use `logger.exception()` for full tracebacks in terminal.
- **Input validation:** All ID parameters validated as 12-char hex strings to prevent path traversal.

## SDLC Process

This project uses a custom SDLC framework with 5 phases (P1→P5). See `.claude/rules/` for details.

- P1: Requirements + Design (user confirms PRD)
- P2: Coding (auto-driven after P1)
- P3: Testing
- P4: Review (single formal gate)
- P5: Delivery

**Quick reference:** `/phase` status, `/review` audit, `/checkpoint` save state

## Conventions

- Backend: Python 3.12+, type hints, `from __future__ import annotations`, Pydantic v2
- Frontend: Vue 3 `<script setup>`, TypeScript strict, Composition API only
- API responses: JSON (REST) or SSE (streaming)
- Persistence: SQLite via `aiosqlite` + LangGraph `AsyncSqliteSaver` checkpointer
- Document metadata: File-based JSON under `data/knowledge_bases/{kb_id}/`
