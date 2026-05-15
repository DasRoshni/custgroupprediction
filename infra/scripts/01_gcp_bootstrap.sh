#!/usr/bin/env bash
# Authenticate, select project, enable APIs, configure Docker auth.
# Required env: PROJECT_ID. Optional: REGION (default us-central1).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID=<your-gcp-project>}"
REGION="${REGION:-us-central1}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud not on PATH. Run: bash infra/scripts/00_install_gcloud.sh" >&2
  exit 1
fi

echo "==> 1. Auth (opens browser if needed)"
gcloud auth login --update-adc --quiet || true

echo "==> 2. Set project + region defaults"
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
gcloud config set artifacts/location "$REGION"

echo "==> 3. Verify billing is enabled (required for Cloud Run + AR + GCS)"
BILLING=$(gcloud beta billing projects describe "$PROJECT_ID" --format='value(billingEnabled)' 2>/dev/null || echo "unknown")
if [ "$BILLING" != "True" ]; then
  cat >&2 <<EOF
ERROR: Billing is not enabled on $PROJECT_ID.
Enable it at: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID
Then re-run this script.
EOF
  exit 1
fi
echo "  Billing: ENABLED"

echo "==> 4. Enable required APIs (~1-2 minutes)"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  serviceusage.googleapis.com

echo "==> 5. Configure docker auth for Artifact Registry"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

cat <<EOF

==> Bootstrap complete.
   Project: $PROJECT_ID
   Region:  $REGION
   Account: $(gcloud config get-value account 2>/dev/null)

Next step: make bq-setup PROJECT_ID=$PROJECT_ID
EOF
