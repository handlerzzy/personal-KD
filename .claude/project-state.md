# SDLC 项目状态（活文档 — 持续更新）

> **COMPACTION 保护区域。** 唯一状态存储，通过 CLAUDE.md @import 加载。升级时不被覆盖。

```yaml
# 项目级（跨任务持久化）
project_roadmap: "基于 LangGraph 的个人知识库问答系统"  # ≤50字
completed_tasks: []  # 精简格式，≥5个时归档
global_architecture: []  # ≤5条

# 当前任务（重置时归档后清空）
current_phase: P5  # P0-P5
task_description: "知识库问答系统全栈开发"  # ≤30字
started_at: "2026-05-30"
last_updated: "2026-05-31 12:00"
requirements_clarification:  # PRD已锁定，此字段保留为空占位
prd_file: ".claude/prd.md"  # PRD 已锁定
architecture_decisions:  # ≤5条
  - "分层模块化: API(FastAPI) → Agent(LangGraph) → 检索/文档/LLM 三层分离"
  - "LangGraph StateGraph 编排: 文档处理→Hybrid检索→Rerank→LLM问答 流程"
  - "每知识库独立隔离: Qdrant collection + bm25x目录 + 独立对话列表"
  - "SSE 双事件流: reasoning_content + content 分别推送，前端分区域渲染"
  - "MinerU PDF解析: Gitee下载本地运行，控制显存<2GB"
modified_files: [".claude/project-state.md", ".claude/prd.md",
  "Makefile", "pyproject.toml", ".gitignore",
  "backend/requirements.txt", "backend/env.example", "backend/app/config.py",
  "backend/app/__init__.py", "backend/app/models/kb.py", "backend/app/models/document.py", "backend/app/models/conversation.py",
  "backend/app/document/__init__.py", "backend/app/document/parser.py", "backend/app/document/chunker.py", "backend/app/document/embedder.py",
  "backend/app/retrieval/__init__.py", "backend/app/retrieval/dense.py", "backend/app/retrieval/sparse.py", "backend/app/retrieval/hybrid.py", "backend/app/retrieval/reranker.py",
  "backend/app/agent/__init__.py", "backend/app/agent/state.py", "backend/app/agent/graph.py",
  "backend/app/agent/nodes/__init__.py", "backend/app/agent/nodes/document_node.py", "backend/app/agent/nodes/retrieval_node.py", "backend/app/agent/nodes/qa_node.py",
  "backend/app/api/__init__.py", "backend/app/api/knowledge_base.py", "backend/app/api/document.py", "backend/app/api/conversation.py", "backend/app/api/chat.py",
  "backend/app/main.py",
  "backend/app/evaluation/__init__.py", "backend/app/evaluation/cli.py",
  "scripts/evaluate.py",
  "frontend/package.json", "frontend/vite.config.ts", "frontend/tsconfig.json", "frontend/index.html",
  "frontend/src/main.ts", "frontend/src/App.vue", "frontend/src/types/index.ts", "frontend/src/api/index.ts",
  "frontend/src/composables/useKb.ts", "frontend/src/composables/useConversation.ts", "frontend/src/composables/useChat.ts",
  "frontend/src/components/Sidebar.vue", "frontend/src/components/ChatView.vue", "frontend/src/components/MessageBubble.vue",
  "frontend/src/components/ThinkingBlock.vue", "frontend/src/components/ChatInput.vue", "frontend/src/components/KbModal.vue",
  "docker-compose.yml", "tests/cases.json"]
todo_items: []
review_retry_count: 0
phase_history: []  # ≥10条时压缩
key_context: "P5交付: 测试21/21通过, ruff lint通过, uv包管理配置完成"  # ≤50字
```

**更新时机**：新任务→归档+重置 | PRD确认→写 prd.md | 阶段推进→更新 phase | 文件修改→记路径 | 架构→记决策 | 压缩前→更新全部

**Compact 保留**：current_phase、task_description、prd_file、modified_files、key_context、project_roadmap、completed_tasks（最近3个）、global_architecture、prd.md文件

**Compact 删除**：phase_history详细、todo_items、多余completed_tasks、requirements_clarification

详见 `.claude/rules/09-memory-management.md`
