#!/usr/bin/env bash
# Manual local smoke: clean DB -> migrate -> seed -> start API -> authenticated request.
# Proves a fresh checkout is usable end-to-end. Run: ./scripts/smoke.sh
set -euo pipefail
cd "$(dirname "$0")/.."

export AIGW_DATABASE_URL="sqlite:///./smoke.db"
trap 'rm -f smoke.db; [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true' EXIT

rm -f smoke.db
echo "==> migrate"
uv run alembic -c control-plane/governance-api/alembic.ini upgrade head >/dev/null

echo "==> seed"
SEED_OUT=$(uv run python scripts/seed.py)
echo "$SEED_OUT"
ORG=$(echo "$SEED_OUT" | awk '/org:/{print $2}')

echo "==> start API"
uv run uvicorn governance_api.main:app --port 8099 >/tmp/aigw-smoke.log 2>&1 &
API_PID=$!
for _ in $(seq 1 30); do curl -sf localhost:8099/healthz >/dev/null && break; sleep 0.3; done

echo "==> authenticated request (list models as org-admin)"
CODE=$(curl -s -o /tmp/aigw-models.json -w "%{http_code}" localhost:8099/api/v1/models \
  -H "X-User-Id: demo" -H "X-Org-Id: $ORG" -H "X-Org-Roles: org-admin")
echo "GET /api/v1/models -> $CODE"
grep -q "demo-gpt" /tmp/aigw-models.json && echo "OK: demo model present" || { echo "FAIL"; exit 1; }
echo "SMOKE PASSED"
