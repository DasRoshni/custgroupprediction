#!/usr/bin/env bash
# Load customerGroups.csv into BigQuery.
# Usage: PROJECT_ID=<id> DATASET=marketing TABLE=campaigns_raw ./load.sh /path/to/customerGroups.csv

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
DATASET="${DATASET:-marketing}"
TABLE="${TABLE:-campaigns_raw}"
LOCATION="${LOCATION:-US}"
GCS_BUCKET="${GCS_BUCKET:-${PROJECT_ID}-marketing-raw}"
SRC_CSV="${1:?usage: ./load.sh <path-to-csv>}"
SCHEMA_FILE="$(dirname "$0")/schema.json"

echo "==> 1/5 Ensure dataset ${PROJECT_ID}:${DATASET} exists"
bq --location="${LOCATION}" --project_id="${PROJECT_ID}" mk \
  --dataset --force \
  --description "Marketing campaign customer-group comparisons" \
  --label env:prod,domain:marketing \
  "${PROJECT_ID}:${DATASET}" || true

echo "==> 2/5 Ensure GCS staging bucket gs://${GCS_BUCKET} exists"
gsutil ls -b "gs://${GCS_BUCKET}" >/dev/null 2>&1 || \
  gsutil mb -l "${LOCATION}" -p "${PROJECT_ID}" "gs://${GCS_BUCKET}/"

echo "==> 3/5 Stage CSV to GCS"
GCS_PATH="gs://${GCS_BUCKET}/campaigns/v1/$(basename "${SRC_CSV}")"
gsutil cp "${SRC_CSV}" "${GCS_PATH}"

echo "==> 4/5 Create table ${PROJECT_ID}:${DATASET}.${TABLE} (if missing)"
bq --project_id="${PROJECT_ID}" mk \
  --table --force \
  --description "Marketing campaign comparisons — raw load" \
  --label env:prod,domain:marketing,pii:none \
  "${PROJECT_ID}:${DATASET}.${TABLE}" \
  "${SCHEMA_FILE}" || true

echo "==> 5/5 Load CSV into BigQuery"
bq --project_id="${PROJECT_ID}" load \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --quote='"' \
  --max_bad_records=0 \
  --replace \
  "${PROJECT_ID}:${DATASET}.${TABLE}" \
  "${GCS_PATH}"

echo "==> Verify row counts by target"
bq --project_id="${PROJECT_ID}" query --use_legacy_sql=false --format=pretty "
SELECT target, COUNT(*) AS n
FROM \`${PROJECT_ID}.${DATASET}.${TABLE}\`
GROUP BY target
ORDER BY target
"

echo "Done."
