# PRD - MinerU PDF解析集成

## 需求
| ID | 需求≤30字 | 验收标准 |
|----|----------|---------|
| R1 | 智能路由选择PDF解析器 | 根据PDF特征自动选择PyMuPDF/MinerU flash/MinerU precision |
| R2 | MinerU flash模式解析 | 简单复杂度PDF用flash模式，无需token，返回Markdown |
| R3 | MinerU precision模式解析 | 复杂PDF用precision模式，需token，支持OCR/公式/表格 |
| R4 | PyMuPDF保持为默认 | 纯文本PDF仍用PyMuPDF，速度快，零依赖 |
| R5 | 解析结果统一为文本 | 三种解析器输出统一格式供下游chunker使用 |

## 技术栈
- langchain-mineru >= 0.1.3（新增）
- mineru-open-sdk >= 0.2.5（新增）
- PyMuPDF（现有）

## 非功能
- MinerU API调用超时≤30s
- 解析失败自动降级到PyMuPDF
- 不阻塞其他文档类型（txt/md）
