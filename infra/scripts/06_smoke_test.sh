#!/usr/bin/env bash
# Hit the live Cloud Run service: /healthz, /readyz, /v1/model/info,
# /v1/predict (happy path), /v1/predict (leakage rejection).
#
# Resolves URL from terraform output if not passed as arg.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if [ "${1:-}" ]; then
  URL="$1"
else
  URL=$(cd "$ROOT/infra/terraform" && terraform output -raw service_url 2>/dev/null || true)
fi

if [ -z "${URL:-}" ]; then
  echo "Usage: $0 <SERVICE_URL>" >&2
  echo "  or run after 'make deploy' so terraform output can resolve it." >&2
  exit 1
fi

echo "Service: $URL"

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; exit 1; }

echo
echo "--- /healthz ---"
curl -fsS "$URL/healthz" | python3 -m json.tool && pass "/healthz returned 200" || fail "/healthz failed"

echo
echo "--- /readyz ---"
RESP=$(curl -fsS "$URL/readyz")
echo "$RESP" | python3 -m json.tool
echo "$RESP" | grep -q '"ready"' && pass "service reports ready" || fail "service not ready"

echo
echo "--- /v1/model/info ---"
curl -fsS "$URL/v1/model/info" | python3 -m json.tool

PAYLOAD="$ROOT/docs/examples/predict_request.json"
if [ -f "$PAYLOAD" ]; then
  echo
  echo "--- /v1/predict (happy path) ---"
  PRED=$(curl -fsS -X POST "$URL/v1/predict" \
    -H 'Content-Type: application/json' -d @"$PAYLOAD")
  echo "$PRED" | python3 -m json.tool
  echo "$PRED" | grep -q '"predicted_group":' && pass "prediction returned" || fail "prediction missing field"

  echo
  echo "--- /v1/predict (leakage attempt — expect 422) ---"
  python3 -c "
import json
p = json.load(open('$PAYLOAD'))
p['g1_21'] = 0.5
print(json.dumps(p))
" > /tmp/cgp_leaky.json
  HTTP=$(curl -s -o /tmp/cgp_resp.json -w '%{http_code}' \
    -X POST "$URL/v1/predict" \
    -H 'Content-Type: application/json' -d @/tmp/cgp_leaky.json)
  python3 -m json.tool /tmp/cgp_resp.json
  [ "$HTTP" = "422" ] && pass "leakage column rejected with $HTTP" \
                      || fail "expected 422, got $HTTP"
fi

echo
echo "==> Smoke test PASSED."
