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

echo "==> Seeding demo data (idempotent)"
uv run python scripts/seed.py || true

echo "==> Starting stub provider on :9099"
uv run python scripts/stub_provider.py &
pids+=($!)

echo "==> Starting governance-api on :8080"
uv run uvicorn governance_api.main:app --reload --port 8080 &
pids+=($!)

# The LiteLLM proxy (data plane) is optional locally — start it only if the
# proxy extra is installed. Run `make proxy` to install it and run standalone.
if uv run --package aigw-hooks python -c "import litellm.proxy.proxy_server" >/dev/null 2>&1; then
  echo "==> Starting LiteLLM proxy on :4000"
  AIGW_LITELLM_CONFIG=./litellm.config.yaml uv run --package aigw-hooks bash data-plane/litellm/entrypoint.sh &
  pids+=($!)
else
  echo "==> LiteLLM proxy extra not installed; skipping data plane (run 'make proxy' for it)"
fi

if [ -d admin-ui ]; then
  echo "==> Starting Vue UI on :5173"
  ( cd admin-ui && (pnpm dev || npm run dev) ) &
  pids+=($!)
else
  echo "==> admin-ui not scaffolded yet; skipping UI"
fi

wait
