# ============================================================
# PersonalKD 多阶段构建镜像
# 阶段1: 前端构建 (Node 24)
# 阶段2: 后端运行时 (Python 3.12 + uv)
# 最终镜像包含后端服务 + 前端静态产物
# ============================================================

# ---------- 阶段1: 构建前端 ----------
FROM node:24-alpine AS frontend-builder

WORKDIR /app/frontend

# 先复制依赖描述文件，利用 Docker 缓存层
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# 复制前端源码并构建
COPY frontend/ ./
RUN npm run build


# ---------- 阶段2: 后端运行时 ----------
FROM python:3.12-slim AS backend

# 安装系统依赖:
# - build-essential: 编译 C 扩展（部分 Python 包需要）
# - libgomp1: PyTorch/OpenMP 运行时依赖（Jina Reranker）
# 安装完成后清理 apt 缓存减小镜像
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# 安装 uv 包管理器
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/backend

# 先复制依赖文件，利用 Docker 缓存层
COPY backend/requirements.txt ./

# 安装 Python 依赖（--no-cache-dir 减小镜像，--system 安装到系统 Python）
RUN uv pip install --no-cache-dir --system -r requirements.txt

# 复制后端源码
COPY backend/ ./

# 复制前端构建产物到后端静态目录（FastAPI 提供静态文件服务）
COPY --from=frontend-builder /app/frontend/dist ./static

# 创建数据目录（运行时通过 volume 挂载覆盖）
RUN mkdir -p data/knowledge_bases data/uploads data/bm25_indexes

# 暴露服务端口
EXPOSE 8000

# 入口: 从 backend/ 目录启动 uvicorn（确保 pydantic-settings 读取到 .env）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
