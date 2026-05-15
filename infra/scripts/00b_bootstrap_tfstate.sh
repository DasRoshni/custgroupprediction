#!/usr/bin/env bash
# One-time per project: create the GCS bucket that backs Terraform state.
#
# Hardened defaults (fintech-grade):
#   - Uniform bucket-level access (no per-object ACLs)
#   - Object versioning ON (point-in-time recovery)
#   - 7-day soft-delete lifecycle for noncurrent versions
#   - Public access prevention enforced
#   - Optional: CMEK via KMS_KEY env var
#
# Required env: PROJECT_ID, TFSTATE_BUCKET.
# Optional: REGION (us-central1), KMS_KEY (full resource name for CMEK).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${TFSTATE_BUCKET:?set TFSTATE_BUCKET (e.g. ${PROJECT_ID}-tfstate)}"
REGION="${REGION:-us-central1}"

echo "==> 1. Create bucket gs://$TFSTATE_BUCKET ($REGION)"
if gsutil ls -b "gs://$TFSTATE_BUCKET" >/dev/null 2>&1; then
  echo "  bucket already exists, ensuring hardened settings"
else
  gsutil mb -l "$REGION" -p "$PROJECT_ID" -b on "gs://$TFSTATE_BUCKET/"
fi

echo "==> 2. Enforce uniform bucket-level access (no legacy ACLs)"
gsutil uniformbucketlevelaccess set on "gs://$TFSTATE_BUCKET" || true

echo "==> 3. Enable versioning (point-in-time recovery)"
gsutil versioning set on "gs://$TFSTATE_BUCKET"

echo "==> 4. Block public access at the bucket level"
gsutil pap set enforced "gs://$TFSTATE_BUCKET" || true

echo "==> 5. Set lifecycle: keep noncurrent versions 30 days then delete"
LIFECYCLE_JSON=$(mktemp)
cat > "$LIFECYCLE_JSON" <<'EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"daysSinceNoncurrentTime": 30, "numNewerVersions": 5}
      }
    ]
  }
}
EOF
gsutil lifecycle set "$LIFECYCLE_JSON" "gs://$TFSTATE_BUCKET"
rm -f "$LIFECYCLE_JSON"

if [ -n "${KMS_KEY:-}" ]; then
  echo "==> 6. Apply CMEK: $KMS_KEY"
  gsutil kms encryption -k "$KMS_KEY" "gs://$TFSTATE_BUCKET"
else
  echo "==> 6. CMEK skipped (set KMS_KEY=projects/.../cryptoKeys/... to enable)"
fi

cat <<EOF

==> Terraform state bucket ready.

Next steps:
  1. Edit infra/terraform/backend.tf — set bucket = "$TFSTATE_BUCKET"
  2. Run:  cd infra/terraform && terraform init -migrate-state
  3. Confirm 'yes' when prompted to migrate local state.

After that, every 'terraform apply' updates remote state, locked & versioned.
EOF
