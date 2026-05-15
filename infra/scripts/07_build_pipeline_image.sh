#!/usr/bin/env bash
# Build & push the Vertex AI pipeline base image to Artifact Registry.
#
# This image is used by every Python function component in the pipeline,
# so each step starts with `customergroups`, `dbt-bigquery`, and Google Cloud
# SDKs already installed (no per-step pip install cost).
#
# Required env: PROJECT_ID. Optional: REGION, IMAGE_TAG.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
APP_NAME="${APP_NAME:-customer-group-predictor}"
IMAGE_TAG="${IMAGE_TAG:-v1.0.0}"
REPO="${APP_NAME}-images"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${APP_NAME}-pipeline:${IMAGE_TAG}"

echo "==> 1. Ensure AR repo exists: $REPO"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker --location="$REGION" \
    --description="Container images for $APP_NAME"

echo "==> 2. Ensure buildx builder"
docker buildx inspect cgp-builder >/dev/null 2>&1 || \
  docker buildx create --name cgp-builder --use --bootstrap
docker buildx use cgp-builder

echo "==> 3. Build (linux/amd64) and push: $IMAGE"
docker buildx build \
  --platform linux/amd64 \
  -f "$ROOT/infra/docker/Dockerfile.pipeline" \
  -t "$IMAGE" \
  --push \
  "$ROOT"

echo
echo "==> Pipeline image pushed: $IMAGE"
echo "Use this in ml_vertex/pipeline.py: PIPELINE_IMAGE = \"${IMAGE}\""
