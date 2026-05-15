#!/usr/bin/env bash
# Provision Cloud Run + supporting GCP infra via Terraform.
#
# Two-stage apply so the Artifact Registry and GCS bucket exist before the
# Cloud Run resource references the image URL.
#
# Required env: PROJECT_ID.
# Optional: REGION, IMAGE_TAG, INVOKER_MEMBER.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
APP_NAME="${APP_NAME:-customer-group-predictor}"
IMAGE_TAG="${IMAGE_TAG:-v1.0.0}"
INVOKER="${INVOKER_MEMBER:-allUsers}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF_DIR="$ROOT/infra/terraform"
cd "$TF_DIR"

# Generate tfvars from env if not already present (or stale).
cat > terraform.tfvars <<EOF
project_id     = "$PROJECT_ID"
region         = "$REGION"
app_name       = "$APP_NAME"
image_tag      = "$IMAGE_TAG"
invoker_member = "$INVOKER"
EOF

echo "==> 1. terraform init"
terraform init -upgrade

echo "==> 2. terraform plan"
terraform plan -out=tfplan

echo "==> 3. terraform apply (auto-approve)"
terraform apply -auto-approve tfplan

echo
echo "==> Deployment complete."
echo "Service URL:"
terraform output -raw service_url
echo
echo "Models bucket:"
terraform output -raw models_bucket
echo
echo "Image repository:"
terraform output -raw image_repository
echo
