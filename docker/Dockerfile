# EasyChat 新架构镜像（单 worker；无 MySQL/Redis/Neo4j/Milvus）
# 构建：docker build -f docker/Dockerfile -t easychat:local .
# 前端构建产物：agent_frontend/dist（npm run build 生成，见 docs/architecture/operations.md）

FROM node:22-alpine AS frontend
WORKDIR /web
COPY agent_frontend/package.json agent_frontend/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY agent_frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    EASYCHAT_DATA_DIR=/app/data \
    EASYCHAT_ROOT=/app \
    PORT=8001

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements-core.txt docker/requirements-hermes.txt ./
RUN pip install --no-cache-dir -r requirements-core.txt \
    && pip install --no-cache-dir -r requirements-hermes.txt

COPY backend/ ./backend/
COPY --from=frontend /web/dist ./static
COPY docs/architecture/operations.md ./docs/architecture/operations.md

RUN mkdir -p /app/data/artifacts /app/data/hermes

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8001/healthz || exit 1

# 单 worker：SQLite + 进程内调度器/worker，不支持多副本共享状态
CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
