# ============================================================
# AgentForge Dockerfile — 后端（跳过前端构建）
# ============================================================
# 用法:
#   docker compose up --build -d agentforge
#   curl http://localhost:8001/health
# ============================================================

FROM python:3.11-slim

LABEL maintainer="AgentForge"
LABEL description="通用 Hermes AI Agent 脚手架"

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    # 文件解析依赖
    poppler-utils \
    libreoffice-core \
    # 清理
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt \
    # 安装 NLTK 数据
    && python -c "import nltk; nltk.download('punkt_tab'); nltk.download('averaged_perceptron_tagger_eng')"

# 复制后端代码
COPY main.py .
COPY backend/ ./backend/
COPY sql/ ./sql/

# 创建运行时目录
RUN mkdir -p /app/data/uploads \
             /app/data/chat_uploads \
             /app/data/kb \
             /app/data/kb_sources \
             /app/data/rag_vectors \
             /app/data/cron_reports \
             /app/data/logs \
             /app/data/hermes

# ── 环境变量 ──
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    HERMES_HOME=/app/data/hermes \
    AGENTFORGE_DATA_DIR=/app/data \
    AGENTFORGE_LOG_DIR=/app/data/logs \
    PORT=8001

EXPOSE 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# 启动
CMD ["python", "main.py"]
