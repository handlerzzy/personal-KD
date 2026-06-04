# PRD - RAG 系统 LangSmith 评估

## 需求

| ID | 需求 | 验收标准 |
|----|------|---------|
| R1 | 构建测试数据集 | 5 篇 PDF 上传到测试 KB，25 个 QA 对导入 LangSmith |
| R2 | 实现 RAG 评估管道 | 支持 Correctness、Groundedness、Retrieval Relevance 三个维度 |
| R3 | 生成评估报告 | 报告包含各维度分数、通过率、失败案例分析 |
| R4 | 检索率优化（条件触发） | 若 Retrieval Relevance < 90%，分析瓶颈并给出优化方案 |

## 技术栈

- LangSmith (evaluation SDK)
- FastAPI + LangGraph (现有后端)
- Qdrant (向量检索)
- ZhipuAI (embedding)
- Jina Reranker v3 (重排序)

## 非功能需求

- 评估脚本可重复执行
- 结果持久化到本地文件
- 评估过程不影响生产环境

## 评估维度

| 维度 | 比较对象 | 需要参考答案？ | 衡量什么 |
|------|---------|--------------|---------|
| Correctness | 生成答案 vs 标准答案 | 需要 | 答案是否事实正确 |
| Groundedness | 生成答案 vs 检索文档 | 不需要 | 答案是否有依据 |
| Retrieval Relevance | 检索文档 vs 用户问题 | 不需要 | 检索结果是否相关 |
