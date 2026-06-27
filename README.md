# Personal Knowledge Base Agent

基于 LangGraph 的个人知识库问答系统。用户上传文档（PDF/TXT/MD），系统自动索引，通过 LLM 结合检索结果生成带源引用的回答。

## 核心架构

采用 5 节点条件 LangGraph 图，根据查询类型动态路由：

```
START → classify_query → [needs_retrieval?]
    [true]  → retrieve → generate_answer → [verify?] → [refine?] → END
    [false] → generate_answer → END
```

| 节点 | 职责 |
|------|------|
| **classify_query** | DashScope qwen-flash 判断查询类型（factual/analytical/multi_hop/summary/chitchat）+ 搜索策略映射 |
| **retrieve** | 并行 Dense（Qdrant）+ Sparse（BM25）检索 → RRF 融合 → Jina Reranker 重排序 |
| **generate_answer** | ChatOpenAI 流式生成带源引用的回答，自定义 `_ReasoningChatOpenAI` 保留思考过程 |
| **verify_answer** | 仅 multi_hop 验证有据性+完整性（阈值 0.7） |
| **refine_answer** | 根据验证反馈精炼回答 |

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **后端框架** | FastAPI + Python 3.12 | REST API + SSE 流式 |
| **Agent 引擎** | LangGraph StateGraph | 5 节点条件图编排 |
| **向量数据库** | Qdrant | 稠密检索 |
| **稀疏检索** | rank_bm25 + jieba 分词 | BM25 关键词检索 |
| **融合** | RRF（Reciprocal Rank Fusion） | Dense + Sparse 融合 |
| **重排序** | Jina Reranker v3（1.2GB） | Cross-Encoder 精排 |
| **Embedding** | ZhipuAI embedding-3 (512维) | 文本向量化 |
| **LLM** | 多 Provider 支持（MiMo / DeepSeek / OpenAI 兼容） | 回答生成（支持推理模式） |
| **LLM Provider 抽象** | `app/llm/providers.py` — 配置表驱动，一行新增 Provider | thinking 参数差异化翻译 |
| **查询分类** | DashScope qwen-flash | 查询类型分类 |
| **PDF 解析** | PyMuPDF + MinerU | 智能路由解析 |
| **持久化** | SQLite（aiosqlite, WAL 模式） | 用户/知识库/对话/消息 |
| **认证** | python-jose (JWT) + bcrypt | 用户认证 + 数据隔离 |
| **前端** | Vue 3 + Vite + TypeScript + Pinia | SPA 单页应用 |
| **容器化** | Docker + docker-compose | 多阶段构建（Node 24 + Python 3.12） |
| **评估** | LangSmith RAGAS | 三维评估 |

## 核心特性

- **Multi-LLM Provider 抽象** — 配置表驱动（一行新增 Provider），自动处理 MiMo/DeepSeek/OpenAI 的 thinking 参数差异
- **JWT 用户认证** — Access Token（2h）+ Refresh Token（7天），bcrypt 密码哈希，静默登录
- **用户数据隔离** — 知识库、对话、消息按用户隔离，API 层统一权限检查
- **智能查询分类与路由** — 自动识别查询类型，按需触发检索和验证
- **混合检索 + RRF 融合** — Dense（Qdrant）+ Sparse（BM25）并行检索，RRF 算法融合，Jina Reranker 重排序
- **HyDE + Multi-Query** — 假设文档嵌入提升匹配精度，查询变体扩展召回
- **MinerU PDF 智能解析** — 复杂度评估自动路由：简单 PDF 用 PyMuPDF，复杂 PDF（扫描件、表格）用 MinerU
- **SSE 双事件流** — reasoning（思考过程）和 content（最终回答）实时分区域渲染
- **LangSmith 评估** — 三维评估（Faithfulness、Answer Correctness、Context Relevance），支持实验追踪与 A/B 测试
- **答案质量闭环** — 梯度验证 + 精炼流程确保回答质量
- **多轮对话历史** — SQLite 持久化对话记录，LangGraph checkpointer 管理 Agent 状态
- **LLM 缓存** — ChatOpenAI 实例缓存 + 启动预热，按 `(streaming, enable_thinking, effort)` 缓存 key
- **检索指标监控** — `MetricsTracker` JSON 日志：score_drop_k、召回利用率、检索延迟
- **答案去重** — 自动检测并移除 LLM 回答中的重复内容（DeepSeek 重复循环保护）
- **安全中间件** — CORS 可配、限流（10次/60秒）、CSP/X-Frame-Options 安全头

## 快速启动

**前置要求：** Python 3.12+, Node.js 20+, Docker

```bash
# 1. 启动 Qdrant 向量数据库
docker-compose up -d

# 2. 配置后端
cp backend/env.example backend/.env
# 编辑 backend/.env，填入 API Keys

# 3. 启动后端
make install-dev
make dev-backend

# 4. 启动前端（新终端）
cd frontend && npm install && npm run dev

# 5. 访问
open http://localhost:5173
```

### 环境变量

参见 `backend/env.example`，必填项：

| 变量 | 说明 |
|------|------|
| `ZHIPU_API_KEY` | ZhipuAI Embedding API Key |
| `LLM_API_BASE` | LLM API 地址 |
| `LLM_API_KEY` | LLM API Key |
| `LLM_MODEL` | LLM 模型名（默认 mimo-v2.5） |
| `LLM_PROVIDER` | Provider 类型：`mimo` / `deepseek` / `openai` |
| `DASHSCOPE_API_KEY` | DashScope API Key（查询分类） |
| `QDRANT_URL` | Qdrant 地址（默认 localhost:6333） |
| `SECRET_KEY` | JWT 签名密钥（生产环境必须设置） |

## LLM Provider 说明

通过 `LLM_PROVIDER` 环境变量切换底层模型，`app/llm/providers.py` 配置表自动处理参数差异：

| Provider | 支持 thinking | effort 级别 | reasoning_content 流式 |
|----------|-------------|-------------|----------------------|
| **MiMo** | `thinking.type: enabled/disabled` | on/off（无分级） | ✓ |
| **DeepSeek** | `thinking.type: enabled` + `reasoning_effort` | `high` / `max` | ✓ |
| **OpenAI 兼容** | 不支持 | — | — |

Thinking 力度在业务层通过 `_QUERY_TYPE_EFFORT` 控制：chitchat=None（不思考）、factual/summary/analytical=high（常规思考）、multi_hop=max（最大思考）。

## 模型说明

项目使用 Jina Reranker v3 进行检索结果重排序（1.2GB），采用 **运行时自动下载** 策略：

- **首次启动**：自动从 [ModelScope](https://modelscope.cn/models/jinaai/jina-reranker-v3) 下载模型到 `backend/models/jina-reranker-v3/`
- **后续启动**：检测到本地模型已存在，直接加载，无需重复下载
- **Docker 部署**：通过 volume 挂载持久化模型目录，容器重建时无需重新下载

### 手动下载（离线环境）

```bash
# 方式 1：使用 modelscope CLI
pip install modelscope
modelscope download --model jinaai/jina-reranker-v3 --local_dir backend/models/jina-reranker-v3

# 方式 2：使用 Python
python -c "from modelscope import snapshot_download; snapshot_download('jinaai/jina-reranker-v3', local_dir='backend/models/jina-reranker-v3')"
```

> **注意**：`backend/models/` 已被 `.gitignore` 排除，不会提交到 Git 仓库。

## Docker 部署

```bash
docker-compose up --build
```

多阶段构建：Stage 1 构建前端（Node 24），Stage 2 构建后端（Python 3.12 slim + uv）并将前端 dist 复制到 `backend/static/`，后端直接托管 SPA 静态文件。

首次启动时会自动下载 Reranker 模型（约 1.2GB），请确保网络通畅。模型通过 volume 挂载持久化，后续重建容器无需重新下载。

访问 `http://localhost:8000`。

## 项目结构

```
backend/app/
├── llm/              # LLM Provider 抽象层
│   └── providers.py    # Provider 配置表 + wire-format 翻译
├── api/              # FastAPI 路由（REST + SSE）
│   ├── auth.py         # 认证 API（注册/登录/刷新/登出/用户信息）
│   ├── chat.py         # POST chat，SSE 流式输出（8 种事件类型）
│   ├── conversation.py # 对话 CRUD + 置顶 + 消息查询
│   ├── document.py     # 文档上传/解析/分块/嵌入
│   └── knowledge_base.py # 知识库 CRUD + Qdrant/BM25 初始化
├── agent/            # LangGraph StateGraph（5 节点条件图）
│   ├── graph.py        # 图构建 + 条件边 + 状态初始化
│   ├── state.py        # AgentState TypedDict
│   ├── metrics.py      # MetricsTracker 指标追踪
│   └── nodes/
│       ├── query_classifier.py  # 查询分类 + 搜索策略
│       ├── retrieval_node.py    # HyDE + Multi-Query + 混合检索
│       ├── qa_node.py           # 流式回答生成（_ReasoningChatOpenAI）
│       └── answer_verifier.py   # 梯度验证 + 精炼
├── document/         # 文档处理（PyMuPDF/MinerU 解析、分块、Embedding）
├── retrieval/        # 检索引擎（Dense、Sparse、Hybrid RRF、Reranker）
├── persistence/      # SQLite 持久化（KB、对话、消息、用户）
│   ├── database.py     # 数据库连接 + 表初始化 + 迁移
│   ├── kb_repo.py      # 知识库 CRUD
│   ├── conv_repo.py    # 对话 CRUD
│   ├── message_repo.py # 消息存储
│   └── user_repo.py    # 用户 CRUD + Token 黑名单
├── models/           # Pydantic 数据模型
├── utils/            # 共享工具（sources 格式化）
├── auth.py           # JWT 认证工具（密码哈希、Token 创建/验证）
├── deps.py           # FastAPI 依赖注入（权限检查）
├── answer_cleaner.py # LLM 输出后处理（去 JSON、去重、去 <think> 标签）
├── llm_cache.py      # LLM 实例缓存 + 预热
├── config.py         # 环境变量配置（含 llm_provider）
└── main.py           # FastAPI 应用入口 + 生命周期管理

frontend/src/
├── api/              # REST + SSE 调用（含认证 Token 管理）
├── stores/           # Pinia 状态管理
│   └── auth.ts       # 认证 Store（Token、用户状态）
├── composables/      # 组合式函数
│   ├── useAuth.ts    # 认证逻辑（登录/注册/登出）
│   ├── useChat.ts    # 聊天逻辑（SSE 流式）
│   ├── useConversation.ts # 对话管理
│   └── useKb.ts      # 知识库管理
├── components/       # Vue 组件
│   ├── Sidebar.vue     # 侧边栏（知识库列表 + 对话列表）
│   ├── ChatView.vue    # 聊天视图（消息列表 + 流式渲染）
│   ├── ChatInput.vue   # 聊天输入框
│   ├── MessageBubble.vue # 消息气泡（Markdown + 引用 + <think> 标签降级）
│   ├── ThinkingBlock.vue # 思维链展示
│   ├── KbModal.vue     # 知识库管理弹窗
│   ├── DocList.vue     # 文档列表
│   ├── Login.vue       # 登录页
│   ├── ChangePassword.vue # 修改密码
│   └── Toast.vue       # 消息提示
└── types/            # TypeScript 接口定义（含 User, TokenResponse）

scripts/
├── rag_evaluation.py       # RAGAS 评估脚本（本地四维评估）
└── langsmith_evaluation.py # LangSmith 评估脚本（云端三维评估 + 实验追踪）
```

## 认证 API

| 方法 | 路径 | 描述 | 认证 |
|------|------|------|------|
| POST | `/api/auth/register` | 用户注册 | 无 |
| POST | `/api/auth/login` | 用户登录 | 无 |
| POST | `/api/auth/refresh` | 刷新 Token | Refresh Token |
| POST | `/api/auth/logout` | 用户登出 | Access Token |
| GET | `/api/auth/me` | 获取用户信息 | Access Token |
| PUT | `/api/auth/me` | 更新用户信息 | Access Token |
| PUT | `/api/auth/password` | 修改密码 | Access Token |

**Token 机制：**
- Access Token: 2 小时有效
- Refresh Token: 7 天有效（记住密码 30 天），token_version 撤销 + jti 黑名单
- 密码: bcrypt 哈希存储，8-20 字符，必须包含大小写字母和数字
- 限流: 登录/注册每 IP 60 秒最多 10 次

## 评估结果

使用 LangSmith 评估框架（LLM-as-Judge）对 100 个 QA 对（5 篇学术论文）进行评估：

| 指标 | 分数 |
|------|------|
| Faithfulness（有据性） | 0.914（86/100 = 86.0%） |
| ContextRelevance（检索相关性） | 0.902（84/100 = 84.0%） |
| AnswerCorrectness（正确性） | 0.749（62/100 = 62.0%） |

运行评估：

```bash
python scripts/langsmith_evaluation.py --generate-dataset  # 运行 RAG pipeline + 上传 LangSmith
python scripts/langsmith_evaluation.py                       # 运行 LangSmith 评估
```

## CI

GitHub Actions 自动化：

- **backend-lint-test**: ruff check + pytest
- **frontend-build**: vue-tsc type check + eslint

触发条件：push 到 main/feature/*，或 PR 到 main。

## License

MIT
