# SDLC 项目状态（活文档 — 持续更新）

> **COMPACTION 保护区域。** 唯一状态存储，通过 CLAUDE.md @import 加载。升级时不被覆盖。

```yaml
# 项目级（跨任务持久化）
project_roadmap: "基于 LangGraph 的个人知识库问答系统"  # ≤50字
completed_tasks:
  - task: "前端Bug修复与功能优化"
    prd_summary: "R1:刷新状态恢复 R2:初始页面输入 R3:对话自动命名 R4:重命名置顶 R5:时间分组 R6:检索加载"
    key_decisions: ["localStorage持久化", "LLM自动生成标题", "右键菜单", "时间分组算法"]
    files_count: 8
    completed_at: "2026-06-07"
  - task: "RAG图6项优化"
    prd_summary: "R1:删除grade节点 R2:DashScope分类 R3:verify仅multi_hop R4:并行embedding R5:分层预热 R6:提示词优化"
    key_decisions: ["删除grade/rewrite节点", "DashScope qwen-flash", "并行embedding批次"]
    files_count: 6
    completed_at: "2026-06-10"
  - task: "Bug修复+RAG提示词优化"
    prd_summary: "R1:AgentState.sources R2:Qdrant稳定哈希 R3:SQLite WAL/busy_timeout R4:LLM缓存 R5:提示词统一引用 R6:BM25缓存 R7:并发限制"
    key_decisions: ["MD5稳定hash", "Semaphore(5)并发限制", "自然语言引用策略", "动态历史窗口"]
    files_count: 15
    completed_at: "2026-06-11"
  - task: "JWT用户认证+数据隔离"
    prd_summary: "R1:用户注册 R2:JWT登录 R3:认证中间件 R4:数据隔离 R5:静默登录 R6:登出 R7:改密 R8:用户信息"
    key_decisions: ["python-jose+bcrypt", "Access 2h+Refresh 7天", "依赖注入权限检查", "Token黑名单"]
    files_count: 25
    completed_at: "2026-06-12"
  - task: "JWT安全加固+上线审查"
    prd_summary: "R1:token_version R2:CORS限制 R3:速率限制 R4:安全Headers R5:刷新令牌撤销 R6:SECRET_KEY强制"
    key_decisions: ["jti+token_version撤销机制", "CORS_ORIGINS环境变量", "内存级IP限流"]
    files_count: 12
    completed_at: "2026-06-12"
  - task: "记住密码功能"
    prd_summary: "R1:登录页复选框 R2:refresh token延长至30天 R3:前端状态持久化"
    key_decisions: ["后端动态过期时间", "localStorage持久化状态"]
    files_count: 4
    completed_at: "2026-06-13"
  - task: "Pinia Auth Store重构"
    prd_summary: "R1:Auth Store R2:Token管理迁移 R3:useAuth composable R4:App.vue重构"
    key_decisions: ["Pinia状态管理", "Store+Composable组合", "保持api层独立"]
    files_count: 5
    completed_at: "2026-06-13"
global_architecture:
  - "分层模块化: API(FastAPI) → Agent(LangGraph) → 检索/文档/LLM 三层分离"
  - "JWT认证: Access 2h + Refresh 7d + token_version撤销 + jti黑名单"
  - "数据隔离: 依赖注入统一user_id过滤 + Qdrant/BM25独立collection"
  - "SSE双事件流: reasoning_content + content分别推送"
  - "前端状态管理: Pinia Store + Composable 组合模式"

# 当前任务（重置时归档后清空）
current_phase: P5  # P0-p5
task_description: "GitHub上线准备与项目清理"  # ≤30字
started_at: "2026-06-18"
last_updated: "2026-06-19"

requirements_clarification:
prd_file: ""
architecture_decisions:  # ≤5条
  - "LangGraph StateGraph 编排: classify→retrieve→generate→verify→END"
  - "SSE 双事件流: reasoning_content + content 分别推送，前端分区域渲染"
  - "梯度验证: analytical(完整性,阈值0.6)+multi_hop(有据性+完整性,阈值0.7)"
modified_files:
  - .gitignore
  - backend/app/models/__init__.py
  - backend/app/models/conversation.py
  - backend/app/models/document.py
  - backend/app/models/kb.py
  - .claude/project-state.md
last_updated: "2026-06-19"
todo_items: []
review_retry_count: 0
phase_history: []
key_context: "CI修复.gitignore models/无前缀匹配误吞backend/app/models/ Python包"
review_fixes: []
```

**更新时机**：新任务→归档+重置 | PRD确认→写 prd.md | 阶段推进→更新 phase | 文件修改→记路径 | 架构→记决策 | 压缩前→更新全部

**Compact 保留**：current_phase、task_description、prd_file、modified_files、key_context、project_roadmap、completed_tasks（最近3个）、global_architecture、prd.md文件

**Compact 删除**：phase_history详细、todo_items、多余completed_tasks、requirements_clarification

详见 `.claude/rules/09-memory-management.md`
