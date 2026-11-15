# AgentGuard API
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENTGUARD_DB=/data/agentguard.db \
    AGENTGUARD_SKIP_DOTENV=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agentguard ./agentguard
COPY api ./api
COPY config ./config
COPY scripts ./scripts

RUN mkdir -p /data && useradd --create-home agentguard && chown agentguard /data
USER agentguard

# Hosting platforms (Render, Fly, ...) pass the port in $PORT.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
