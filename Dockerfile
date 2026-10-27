# syntax=docker/dockerfile:1
# SCARVEL — imagem única (frontend React + backend FastAPI) na porta 8000

# ---------- Estágio 1: build do frontend ----------
FROM node:20-bookworm-slim AS web
WORKDIR /web
# yarn.lock é opcional: se existir no repositório, usa versões travadas
COPY frontend/package.json frontend/yarn.lock* ./
RUN if [ -f yarn.lock ]; then yarn install --frozen-lockfile --network-timeout 600000; \
    else yarn install --network-timeout 600000; fi
COPY frontend/ ./
# API por caminho relativo (/api) — sem URL fixa
ENV REACT_APP_BACKEND_URL="" GENERATE_SOURCEMAP=false NODE_OPTIONS=--max-old-space-size=4096
RUN rm -f .env && yarn build

# ---------- Estágio 2: runtime ----------
FROM python:3.11-slim
ARG VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/app \
    APP_VERSION=${VERSION} \
    STATIC_DIR=/app/static \
    DATA_DIR=/app/data \
    TZ=America/Sao_Paulo
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN grep -vE '^(emergentintegrations|litellm)' /tmp/requirements.txt > /tmp/req.prod.txt \
 && pip install --no-cache-dir -r /tmp/req.prod.txt \
 && rm -f /tmp/requirements.txt /tmp/req.prod.txt

COPY backend/ /app/app/
RUN rm -rf /app/app/tests /app/app/.env /app/app/__pycache__ /app/app/*/__pycache__ /app/app/pytest.ini
COPY --from=web /web/build /app/static

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin scarvel \
 && mkdir -p /app/data \
 && chown -R scarvel:scarvel /app/data
USER scarvel

EXPOSE 8000
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "server:app", "--app-dir", "/app/app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*", "--no-server-header", "--log-level", "info"]
