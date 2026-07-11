#!/usr/bin/env bash
# Run the local dev stack (governance-api + Vue UI) concurrently.
# The LiteLLM proxy is added to this script in M3.
set -euo pipefail

cd "$(dirname "$0")/.."

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "==> Applying migrations"
uv run alembic -c control-plane/governance-api/alembic.ini upgrade head

echo "==> Starting governance-api on :8080"
uv run uvicorn governance_api.main:app --reload --port 8080 &
pids+=($!)

if [ -d admin-ui ]; then
  echo "==> Starting Vue UI on :5173"
  ( cd admin-ui && (pnpm dev || npm run dev) ) &
  pids+=($!)
else
  echo "==> admin-ui not scaffolded yet; skipping UI"
fi

wait
