#!/usr/bin/env bash
# Build the API container for linux/amd64 and push to Artifact Registry.
#
# Required env: PROJECT_ID.
# Optional: REGION (us-central1), APP_NAME (customer-group-predictor),
#           IMAGE_TAG (v1.0.0).
#
# On Apple Silicon, this uses buildx to cross-compile for amd64 (Cloud Run target).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
APP_NAME="${APP_NAME:-customer-group-predictor}"
IMAGE_TAG="${IMAGE_TAG:-v1.0.0}"
REPO="${APP_NAME}-images"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${APP_NAME}:${IMAGE_TAG}"

echo "==> 1. Ensure Artifact Registry repo exists: $REPO"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Container images for $APP_NAME"

echo "==> 2. Ensure buildx builder is available"
docker buildx inspect cgp-builder >/dev/null 2>&1 || \
  docker buildx create --name cgp-builder --use --bootstrap

docker buildx use cgp-builder

echo "==> 3. Build (linux/amd64) and push: $IMAGE"
docker buildx build \
  --platform linux/amd64 \
  -f "$ROOT/infra/docker/Dockerfile" \
  -t "$IMAGE" \
  --push \
  "$ROOT"

echo
echo "==> Image pushed: $IMAGE"
echo "Use this tag in terraform.tfvars: image_tag = \"$IMAGE_TAG\""
