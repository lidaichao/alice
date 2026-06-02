# Alice V2.0 AI Bridge — 生产环境 Dockerfile
# 构建: docker build -t alice-ai-bridge:v2 .
# 运行: docker run -d -p 9099:9099 --env-file .env alice-ai-bridge:v2

FROM python:3.11-slim

LABEL maintainer="Alice Team"
LABEL description="Alice V2.0 AI Bridge — LlamaIndex 层级检索 + ReAct Tool Calling"

# 安装 SVN 客户端（解决本地依赖痛点）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        subversion \
        && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建非 root 用户运行
RUN useradd -m -s /bin/bash alice && chown -R alice:alice /app
USER alice

# 暴露端口
EXPOSE 9099

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:9099/health')" || exit 1

# 生产启动（gunicorn 优于 Waitress）
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:9099", "--timeout", "120", "--worker-class", "sync", "ai_bridge:app"]
