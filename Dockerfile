# The whole site as one service: the API serves the built frontend. docs/DEPLOY.md explains it;
# docker-compose.yml is the separate two-container setup for local use.
FROM node:22-alpine AS frontend
WORKDIR /app
# Same origin: the page calls /api on the host that served it.
ENV VITE_USE_MOCK=false \
    VITE_API_URL=""
COPY web/package.json web/package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY web/index.html web/tsconfig.json web/vite.config.ts ./
COPY web/src ./src
COPY web/public ./public
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PARSLEY_WEB_DIST=/app/web/dist
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install '.[web]'
COPY --from=frontend /app/dist ./web/dist

RUN useradd --create-home --uid 10001 parsley
USER parsley
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=2).close()"
# No access log: a URL can hold a session id. One process, because the limits are counted in memory.
CMD ["sh", "-c", "exec python -m uvicorn parsley.web.app:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log --no-server-header"]
