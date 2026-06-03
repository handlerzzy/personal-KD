# SDLC 项目状态（活文档 — 持续更新）

> **COMPACTION 保护区域。** 唯一状态存储，通过 CLAUDE.md @import 加载。升级时不被覆盖。

```yaml
# 项目级（跨任务持久化）
project_roadmap: "基于 LangGraph 的个人知识库问答系统"  # ≤50字
completed_tasks:
  - task: "MinerU PDF解析集成"
    prd_summary: "R1:智能路由 R2:flash模式 R3:precision模式 R4:PyMuPDF保持 R5:统一输出"
    key_decisions: ["langchain-mineru", "复杂度评估算法", "降级策略"]
    files_count: 4
    completed_at: "2026-06-03"
  - task: "LangGraph流式接口改造"
    prd_summary: "R1:graph.astream R2:checkpointer生效 R3:SSE事件不变 R4:ChatOpenAI替代httpx"
    key_decisions: ["stream_mode=updates+messages", "ChatOpenAI统一LLM调用", "checkpointer手动连接管理"]
    files_count: 4
    completed_at: "2026-06-01"
  - task: "Agent持久化迁移SQLite+Checkpointer"
    prd_summary: "R1:SQLite持久化 R2:LangGraph checkpointer R3:安全审查修复"
    key_decisions: ["AsyncSqliteSaver", "persistence模块化", "路径穿越防护"]
    files_count: 11
    completed_at: "2026-05-31"
global_architecture: []  # ≤5条

# 当前任务（重置时归档后清空）
current_phase: P5  # P0-p5
task_description: "MinerU PDF解析集成"  # ≤30字
started_at: "2026-06-01"
last_updated: "2026-06-03 11:55"
requirements_clarification:
prd_file: ""
architecture_decisions:  # ≤5条
  - "分层模块化: API(FastAPI) → Agent(LangGraph) → 检索/文档/LLM 三层分离"
  - "LangGraph StateGraph 编排: 文档处理→Hybrid检索→Rerank→LLM问答 流程"
  - "每知识库独立隔离: Qdrant collection + bm25x目录 + 独立对话列表"
  - "SSE 双事件流: reasoning_content + content 分别推送，前端分区域渲染"
  - "MinerU PDF解析: Gitee下载本地运行，控制显存<2GB"
  - "LangGraph astream双模式流式: updates(sources)+messages(tokens), ChatOpenAI统一LLM调用"
modified_files: [".claude/project-state.md", ".claude/prd.md", ".claude/prd-mineru-integration.md",
  "Makefile", "pyproject.toml", ".gitignore",
  "backend/requirements.txt", "backend/env.example", "backend/app/config.py",
  "backend/app/__init__.py", "backend/app/models/kb.py", "backend/app/models/document.py", "backend/app/models/conversation.py",
  "backend/app/document/__init__.py", "backend/app/document/parser.py", "backend/app/document/chunker.py", "backend/app/document/embedder.py",
  "backend/app/retrieval/__init__.py", "backend/app/retrieval/dense.py", "backend/app/retrieval/sparse.py", "backend/app/retrieval/hybrid.py", "backend/app/retrieval/reranker.py",
  "backend/app/agent/__init__.py", "backend/app/agent/state.py", "backend/app/agent/graph.py",
  "backend/app/agent/nodes/__init__.py", "backend/app/agent/nodes/document_node.py", "backend/app/agent/nodes/retrieval_node.py", "backend/app/agent/nodes/qa_node.py",
  "backend/app/persistence/__init__.py", "backend/app/persistence/database.py", "backend/app/persistence/kb_repo.py",
  "backend/app/persistence/conv_repo.py", "backend/app/persistence/message_repo.py",
  "backend/app/api/__init__.py", "backend/app/api/knowledge_base.py", "backend/app/api/document.py", "backend/app/api/conversation.py", "backend/app/api/chat.py",
  "backend/app/main.py",
  "frontend/package.json", "frontend/vite.config.ts", "frontend/tsconfig.json", "frontend/index.html",
  "frontend/src/main.ts", "frontend/src/App.vue", "frontend/src/types/index.ts", "frontend/src/api/index.ts",
  "frontend/src/composables/useKb.ts", "frontend/src/composables/useConversation.ts", "frontend/src/composables/useChat.ts",
  "frontend/src/components/Sidebar.vue", "frontend/src/components/ChatView.vue", "frontend/src/components/MessageBubble.vue",
  "frontend/src/components/Toast.vue", "frontend/src/components/DocList.vue",
  "frontend/src/components/ThinkingBlock.vue", "frontend/src/components/ChatInput.vue", "frontend/src/components/KbModal.vue",
  "docker-compose.yml", "tests/cases.json",
  "backend/tests/test_parser_mineru.py"]
todo_items: []
review_retry_count: 0
phase_history: []  # ≥10条时压缩
key_context: "MinerU集成完成+bug修复: token传递、import降级、Makefile修复, 全部测试通过"  # ≤50字
```

**更新时机**：新任务→归档+重置 | PRD确认→写 prd.md | 阶段推进→更新 phase | 文件修改→记路径 | 架构→记决策 | 压缩前→更新全部

**Compact 保留**：current_phase、task_description、prd_file、modified_files、key_context、project_roadmap、completed_tasks（最近3个）、global_architecture、prd.md文件

**Compact 删除**：phase_history详细、todo_items、多余completed_tasks、requirements_clarification

详见 `.claude/rules/09-memory-management.md`
