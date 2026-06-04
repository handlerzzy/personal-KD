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
  - task: "RAG系统本地评估"
    prd_summary: "R1:25QA测试集 R2:三维度评估 R3:评估报告 R4:检索率优化"
    key_decisions: ["本地评估替代LangSmith", "三合一评估器", "SOCKS代理兼容"]
    files_count: 9
    completed_at: "2026-06-03"
  - task: "RAGAS专业评估框架集成"
    prd_summary: "R1:100QA测试集 R2:RAGAS四维评估 R3:评估报告 R4:检索率分析优化"
    key_decisions: ["RAGAS框架", "LangchainLLMWrapper", "max_workers=1限流防护"]
    files_count: 4
    completed_at: "2026-06-04"
global_architecture: []  # ≤5条

# 当前任务（重置时归档后清空）
current_phase: P5  # P0-p5
task_description: "RAGAS专业评估框架集成"  # ≤30字
started_at: "2026-06-03"
last_updated: "2026-06-04 22:30"
requirements_clarification:
prd_file: ""
architecture_decisions:  # ≤5条
  - "分层模块化: API(FastAPI) → Agent(LangGraph) → 检索/文档/LLM 三层分离"
  - "LangGraph StateGraph 编排: 文档处理→Hybrid检索→Rerank→LLM问答 流程"
  - "每知识库独立隔离: Qdrant collection + bm25x目录 + 独立对话列表"
  - "SSE 双事件流: reasoning_content + content 分别推送，前端分区域渲染"
  - "MinerU PDF解析: Gitee下载本地运行，控制显存<2GB"
  - "LangGraph astream双模式流式: updates(sources)+messages(tokens), ChatOpenAI统一LLM调用"
modified_files: ["scripts/rag_evaluation.py", ".claude/project-state.md",
  "backend/app/agent/nodes/qa_node.py", "backend/app/agent/nodes/retrieval_node.py",
  "backend/app/document/embedder.py", "backend/app/retrieval/dense.py",
  ".claude/delivery-ragas-evaluation.md"]
todo_items: []
review_retry_count: 0
phase_history: []  # ≥10条时压缩
key_context: "RAGAS评估完成: 100QA评估报告已生成"  # ≤50字
```

**更新时机**：新任务→归档+重置 | PRD确认→写 prd.md | 阶段推进→更新 phase | 文件修改→记路径 | 架构→记决策 | 压缩前→更新全部

**Compact 保留**：current_phase、task_description、prd_file、modified_files、key_context、project_roadmap、completed_tasks（最近3个）、global_architecture、prd.md文件

**Compact 删除**：phase_history详细、todo_items、多余completed_tasks、requirements_clarification

详见 `.claude/rules/09-memory-management.md`
