#!/usr/bin/env bash
# Upload the trained model artifact to GCS in both a versioned and 'current/' prefix.
# Cloud Run reads from 'current/' (atomic swap for zero-downtime promotion).
#
# Required env: PROJECT_ID.
# Optional: REGION (us-central1), APP_NAME (customer-group-predictor),
#           BUCKET (${PROJECT_ID}-${APP_NAME}-models).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
APP_NAME="${APP_NAME:-customer-group-predictor}"
BUCKET="${BUCKET:-${PROJECT_ID}-${APP_NAME}-models}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODEL="$ROOT/ml/artifacts/model.joblib"
META="$ROOT/ml/artifacts/metadata.json"

[ -f "$MODEL" ] || { echo "ERROR: $MODEL missing. Run: make pipeline" >&2; exit 1; }
[ -f "$META" ]  || { echo "ERROR: $META missing. Run: make pipeline"  >&2; exit 1; }

VERSION=$(python3 -c "import json; print(json.load(open('$META'))['model_version'])")
SHA=$(python3 -c "import json; print(json.load(open('$META'))['artifact_sha256'][:12])")

echo "==> 1. Ensure bucket gs://$BUCKET exists (versioned)"
if ! gsutil ls -b "gs://$BUCKET" >/dev/null 2>&1; then
  gsutil mb -l "$REGION" -p "$PROJECT_ID" "gs://$BUCKET/"
  gsutil versioning set on "gs://$BUCKET/"
fi

echo "==> 2. Upload versioned copy: v$VERSION ($SHA)"
gsutil cp "$MODEL" "gs://$BUCKET/v$VERSION/model.joblib"
gsutil cp "$META"  "gs://$BUCKET/v$VERSION/metadata.json"

echo "==> 3. Atomic swap to current/"
gsutil cp "$MODEL" "gs://$BUCKET/current/model.joblib"
gsutil cp "$META"  "gs://$BUCKET/current/metadata.json"

cat <<EOF

==> Model uploaded.
   Versioned: gs://$BUCKET/v$VERSION/
   Current:   gs://$BUCKET/current/   (loaded by Cloud Run on startup)
EOF
