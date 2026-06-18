# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


## ** User Requirements(Very Important) **

1. The user requests that Claude Code uses the project's virtual environment at `/home/handler/文档/learning/projects/personalKD/.venv` in scenarios that require an execution environment, such as testing or running code.

2. The installed dependencies need to synchronize two files: `pyproject.toml` 
in the root directory and `requirements.txt` in the `/backend` subdirectory.

3. When using langsmith or other packages, you need to query their latest APIs through the `context7` plugin.

4. Every time the code is modified, you must use plugin:`security-guidance` for a security review and plugin:`code-review`for a code review.

5. The user is running Linux, where read/write rules containing wildcard patterns are not supported.


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
pytest tests/test_xxx.py -v  # Run single test file
pytest -k "test_name" -v    # Run test by name pattern

# Frontend build
cd frontend && npm run build # Vue-tsc + Vite production build

# Docker deployment
docker-compose up --build    # Build and run full stack (Qdrant + backend + frontend static)
```

**Backend .env** must be in `backend/` directory (pydantic-settings reads it from CWD). See `backend/env.example` for required vars: ZHIPU_API_KEY, LLM_API_BASE, LLM_API_KEY, LLM_MODEL, DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, QDRANT_URL.

**Evaluation:** `scripts/rag_evaluation.py` runs RAGAS framework evaluation (faithfulness, answer_relevancy, context_precision, context_recall) against `data/evaluation/` test set. CLI: `--stage pipeline|eval`, `--rebuild-kb`, `--sample-size`.

## Architecture

### Backend (`backend/app/`)

```
api/           → FastAPI route handlers (REST + SSE streaming)
  chat.py        POST chat endpoint with SSE streaming (8 event types)
  conversation.py  CRUD for conversations + messages + pin toggle
  document.py    Upload/parse/chunk/embed pipeline (PDF/TXT/MD)
  knowledge_base.py  CRUD for knowledge bases + Qdrant/BM25 setup
agent/         → LangGraph StateGraph: classify → retrieve → generate → verify → refine
  nodes/
    query_classifier.py   DashScope qwen-flash query type + search strategy
    retrieval_node.py     HyDE + Multi-Query + dense/sparse → RRF → reranker
    qa_node.py            Streaming answer gen with _ReasoningChatOpenAI
    answer_verifier.py    Gradient verification + refinement
  graph.py       5-node conditional graph with checkpointer
  state.py       AgentState TypedDict
document/      → parser (PyMuPDF/MinerU), chunker (LangChain 500 chars), embedder (ZhipuAI)
retrieval/     → dense (Qdrant), sparse (bm25x), hybrid (RRF fusion), reranker (Jina v3)
persistence/   → SQLite (aiosqlite) + repositories
  database.py    Singleton connection, WAL mode, schema migrations
  kb_repo.py     KnowledgeBase CRUD
  conv_repo.py   Conversation CRUD + pin toggle
  message_repo.py  Message storage with reasoning_content + sources
utils/
  sources.py     Shared build_sources() for formatting retrieved docs
answer_cleaner.py  Strip pipeline metadata from LLM output
llm_cache.py     ChatOpenAI instance cache + warmup (avoids 15-20s cold start)
config.py        Pydantic BaseSettings (env vars + directory constants)
main.py          FastAPI app + lifespan (DB init, checkpointer, warmup)
```

**Agentic RAG pipeline (5-node conditional graph):**
```
START → classify_query → [needs_retrieval?]
    [true]  → retrieve → generate_answer → [verify?] → [refine?] → END
    [false] → generate_answer → END
```
- `classify_query`: DashScope qwen-flash determines query type (factual/analytical/multi_hop/summary) and search strategy (HyDE, multi-query count)
- `retrieve`: Parallel dense+sparse retrieval → RRF fusion → Jina reranker (top_n=10). HyDE generates hypothetical answer for better embedding match; multi-query generates query variations
- `generate_answer`: ChatOpenAI (mimo-v2.5) with streaming. Custom `_ReasoningChatOpenAI` subclass preserves `reasoning_content` from streaming deltas (upstream LangChain discards it). Dynamic thinking budget and history window per query type
- `verify_answer`: Gradient verification — analytical: completeness only (threshold 0.6); multi_hop: faithfulness + completeness (threshold 0.7)
- `refine_answer`: Polishes verified answers based on feedback

Uses `graph.astream(stream_mode=["updates","messages"])` — updates yield sources from retrieve node, messages yield token-level `AIMessageChunk` from qa node. Checkpointer (`AsyncSqliteSaver`) with WAL mode writes state on every invocation.

**SSE streaming event types:** `user_message`, `searching`, `sources`, `reasoning`, `answer`, `done`, `title_update`, `error`.

**Startup warmup:** Three background tasks on startup — LLM warmup (avoids MiMo cold start 15-20s → 2-4s), reranker model preload, jieba dictionary init.

**Persistence:** SQLite database (`data/agent.db`) stores KB metadata, conversations, and messages. Schema migrations handle column additions (is_pinned, message_count, reasoning_content, sources). LangGraph `AsyncSqliteSaver` checkpointer manages agent state for conversation history. Document metadata and uploaded files remain file-based under `data/knowledge_bases/{kb_id}/`.

**Data isolation:** Each KB gets its own Qdrant collection (`kb_{id}`) + BM25 index directory. All metadata in SQLite with foreign key cascades.

### Frontend (`frontend/src/`)

```
api/index.ts          → All REST + SSE streaming calls (native fetch + ReadableStream)
composables/          → useKb, useConversation, useChat (state management, no Vuex/Pinia)
components/           → Sidebar, ChatView, MessageBubble, ThinkingBlock, ChatInput,
                        KbModal, DocList, Toast
types/index.ts        → TypeScript interfaces (KnowledgeBase, KBDocument, Conversation, Message, Source)
```

**State flow:** `App.vue` orchestrates composables → passes props/events to child components. SSE streaming accumulates tokens in real-time via `useChat` refs. Race condition guard (`sendingNewMessage` ref) prevents message fetch conflicts during send. localStorage persists last selected KB.

### Key Patterns

- **LLM cache:** `llm_cache.py` caches ChatOpenAI instances keyed by (streaming, enable_thinking, thinking_budget). Three factories: `get_llm()` (main with thinking), `get_simple_llm()` (auxiliary tasks), `get_dashscope_llm()` (fast classification)
- **Answer cleaner:** `answer_cleaner.py` shared post-processing strips JSON metadata, verification scores, citation refs, fallback fragments from LLM output. Used by both qa_node and chat SSE endpoint
- **Shared sources builder:** `utils/sources.py` `build_sources()` formats retrieved docs into frontend payload, eliminating duplicate code
- **SQLite persistence:** KB metadata, conversations, and messages stored in `data/agent.db`. WAL journal mode, busy_timeout=5000, foreign keys ON
- **File-based document storage:** Uploaded files and document metadata remain JSON under `data/knowledge_bases/{kb_id}/`
- **MinerU PDF parsing:** Complex PDFs (scanned, tables) routed to MinerU; simple PDFs use PyMuPDF. Complexity score determines routing
- **Embedding batching:** ZhipuAI API limits 64 texts/request; `embed_texts()` batches automatically
- **Reranker graceful fallback:** If Jina model fails to load, reranking is skipped (returns top-N from fusion)
- **Logging:** All `try/except` blocks use `logger.exception()` for full tracebacks. Per-module log level overrides via `LOG_LEVELS` env var
- **Input validation:** All ID parameters validated as 12-char hex strings to prevent path traversal

## Docker Deployment

Multi-stage Dockerfile: Stage 1 builds frontend (Node 18), Stage 2 builds backend (Python 3.12 slim) and copies frontend dist into `backend/static/`. The backend serves the SPA with static file fallback.

```bash
docker-compose up --build   # Qdrant + backend (serves frontend static files)
```

`docker-compose.yml` mounts `./data` (SQLite, knowledge bases, uploads, BM25 indexes) and `./backend/models` (reranker) as persistent volumes.

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on push to main/feature/* and PRs:
- **backend-lint-test:** uv + Python 3.12, `ruff check` + `pytest`
- **frontend-build:** Node 18, `npm run build` (type check) + `npx eslint`

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
- Testing: pytest + pytest-asyncio, asyncio_mode auto
- Linting: ruff (backend, line-length 100), eslint (frontend)
