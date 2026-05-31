# PRD - 知识库问答系统

## 需求

| ID | 需求 | 验收标准 |
|----|------|---------|
| R1 | 多知识库管理(CRUD) | 建/删/改/查命名知识库，数据隔离 |
| R2 | 文档上传与解析 | 上传 PDF(MinerU解析)→TXT/MD(LangChain分块)，持久化 |
| R3 | 混合检索 | Dense(Qdrant) + BM25(bm25x) → RRF → Jina Reranker v3 精排 |
| R4 | 流式问答输出 | SSE 逐 token 推送，逐字显示回答 |
| R5 | 思考过程展示 | 消费 `reasoning_content`，前端可折叠展示 |
| R6 | 对话管理(知识库内) | 每个知识库支持多对话，可新建/切换/删除 |
| R7 | Agent 评估 | LangSmith + CLI 脚本，正确性/有据性/检索相关性 |
| R8 | 前端界面 | 左侧对话历史 + 右侧全高对话框(类似DeepSeek) |

## 技术栈

- FastAPI + LangChain + LangGraph
- MinerU(Gitee, PDF解析) + Qdrant(Docker) + bm25x(Rust独立索引)
- Jina Reranker v3(魔塔本地) + 智谱 Embedding-3(512维) + mimo-v2.5
- Vue 3 + Vite + TypeScript
- LangSmith + CLI 评估

## 非功能

- 检索: 端到端<3s(RRF+CrossEncoder)
- 知识库隔离: Qdrant collection + bm25x独立目录
- 流式: SSE, 首 token <500ms
- 部署: 混合模式(Qdrant Docker, 其余手动)
- 资源: 16GB RAM + 6GB VRAM，Reranker/LLM 需控制显存

## UI设计

```yaml
ui_design:
  style: "AI-Native UI / Exaggerated Minimalism"
  colors: "AI Purple(#6366F1) + Slate灰阶中性色"
  fonts: {heading: "Fira Code", body: "Fira Sans"}
  components: "自建Vue3组件"
  prototype: "/tmp/prototype-kb-agent.html"
  responsive: [375px, 768px, 1440px]
```

## 架构概览

```
[Vue3 Frontend] ↔ SSE ↔ [FastAPI] ↔ [LangGraph Agent]
  ┌──────────┐              ├── KnowledgeBase API
  │ 对话列表  │              ├── Document API (MinerU)
  │ (知识库内)│              ├── Conversation API
  │          │              └── Chat API (SSE stream)
  │ 对话框   │                    │
  │ (流式渲染)│    ┌───────────────┼───────────────┐
  │          │    ▼               ▼               ▼
  │ 思考过程 │ Qdrant         bm25x          Jina Reranker
  │ (折叠)   │ (Docker)   (独立目录/知识库)   v3(本地模型)
  └──────────┘
               Embedding-3 API ← 智谱 → LLM: mimo-v2.5 API
```
