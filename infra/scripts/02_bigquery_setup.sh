#!/usr/bin/env bash
# Provision BigQuery for the customer-group dataset.
#
# What this does:
#   1. Create dataset: marketing
#   2. Create staging table (with lineage + DQ columns) — production-shaped
#   3. Create raw table (strict schema)
#   4. Upload CSV to GCS
#   5. Load CSV into raw table (direct, since the source data is already clean)
#   6. Verify row counts
#
# The staging table is created so the full DQ-gated pipeline is ready for
# future loads. For this initial PoC load we go straight to raw.
#
# Required env: PROJECT_ID.
# Optional: REGION (us-central1), BQ_LOCATION (US), DATASET (marketing),
#           RAW_TABLE (campaigns_raw), STG_TABLE (campaigns_stg),
#           GCS_BUCKET (${PROJECT_ID}-marketing-raw).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
LOCATION="${BQ_LOCATION:-US}"
DATASET="${DATASET:-marketing}"
RAW_TABLE="${RAW_TABLE:-campaigns_raw}"
STG_TABLE="${STG_TABLE:-campaigns_stg}"
GCS_BUCKET="${GCS_BUCKET:-${PROJECT_ID}-marketing-raw}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC_CSV="${1:-$ROOT/data/raw/customerGroups.csv}"
SCHEMA_DIR="$ROOT/infra/bigquery"

[ -f "$SRC_CSV" ] || { echo "ERROR: $SRC_CSV not found" >&2; exit 1; }

echo "==> 1. Dataset $PROJECT_ID:$DATASET ($LOCATION)"
bq --location="$LOCATION" --project_id="$PROJECT_ID" mk \
  --dataset --force \
  --description "Marketing campaign customer-group comparisons" \
  --label "env:prod" --label "domain:marketing" \
  "$PROJECT_ID:$DATASET" 2>&1 | grep -v "already exists" || true

echo "==> 2. Staging table (production-shaped — DQ + lineage)"
sed "s/\${PROJECT_ID}/$PROJECT_ID/g" "$SCHEMA_DIR/create_staging_table.sql" | \
  bq query --use_legacy_sql=false --project_id="$PROJECT_ID" --quiet || true

echo "==> 3. Raw table (strict schema). Drop+recreate so schema stays in sync."
bq --project_id="$PROJECT_ID" rm -f -t "$PROJECT_ID:$DATASET.$RAW_TABLE" 2>/dev/null || true
bq --project_id="$PROJECT_ID" mk \
  --table \
  --description "Marketing campaign comparisons — raw load (strict schema)" \
  --label "env:prod" --label "domain:marketing" --label "pii:none" \
  "$PROJECT_ID:$DATASET.$RAW_TABLE" \
  "$SCHEMA_DIR/schema.json"

echo "==> 4. GCS bucket gs://$GCS_BUCKET"
gsutil ls -b "gs://$GCS_BUCKET" >/dev/null 2>&1 || \
  gsutil mb -l "$REGION" -p "$PROJECT_ID" "gs://$GCS_BUCKET/"

GCS_PATH="gs://$GCS_BUCKET/campaigns/v1/$(basename "$SRC_CSV")"
echo "==> 5. Stage CSV to $GCS_PATH"
gsutil cp "$SRC_CSV" "$GCS_PATH"

echo "==> 6. Load CSV into $RAW_TABLE (replace mode)"
bq --project_id="$PROJECT_ID" load \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --quote='"' \
  --max_bad_records=0 \
  --replace \
  "$PROJECT_ID:$DATASET.$RAW_TABLE" \
  "$GCS_PATH"

echo "==> 7. Verify row counts"
bq --project_id="$PROJECT_ID" query --use_legacy_sql=false --format=pretty "
SELECT target, COUNT(*) AS n
FROM \`$PROJECT_ID.$DATASET.$RAW_TABLE\`
GROUP BY target
ORDER BY target
"

cat <<EOF

==> BigQuery setup complete.
   Dataset: $PROJECT_ID:$DATASET
   Raw:     $PROJECT_ID:$DATASET.$RAW_TABLE
   Staging: $PROJECT_ID:$DATASET.$STG_TABLE
   Bucket:  gs://$GCS_BUCKET

Expected counts: 0 -> 1667, 1 -> 3076, 2 -> 1877 (total 6620).
EOF
