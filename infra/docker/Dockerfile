# syntax=docker/dockerfile:1.7
# Multi-stage build — small final image, no build toolchain in runtime layer.

# ----- 1. Builder ------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# OpenMP is required at runtime by xgboost.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first (better layer caching)
COPY api/requirements.txt /build/api-requirements.txt
COPY ml/pyproject.toml /build/ml/pyproject.toml

# Install api runtime deps + customergroups package (no scipy/jupyter/shap)
COPY ml/src /build/ml/src
RUN pip install --upgrade pip \
 && pip install -r /build/api-requirements.txt \
 && pip install /build/ml \
 && pip install google-cloud-storage==2.18.2

# ----- 2. Runtime ------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONPATH=/app/src

RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 1000 app \
 && useradd  --uid 1000 --gid app --shell /bin/bash --create-home app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy the app source and the trained model artifact.
# In prod, MODEL_PATH=gs://... and the GcsJoblibLoader pulls at startup;
# we still bake the artifact in for offline / cold-start fallback.
COPY api/src/ /app/src/
COPY ml/artifacts/model.joblib    /app/artifacts/model.joblib
COPY ml/artifacts/metadata.json   /app/artifacts/metadata.json

# Default to baked-in artifact unless overridden by env.
ENV MODEL_PATH=/app/artifacts/model.joblib \
    METADATA_PATH=/app/artifacts/metadata.json \
    LOG_LEVEL=INFO \
    ENVIRONMENT=prod

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -sf http://localhost:${PORT}/healthz || exit 1

# Cloud Run sends SIGTERM and waits up to ~10s — uvicorn handles that gracefully.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --workers 1
