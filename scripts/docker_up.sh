#!/usr/bin/env bash
# Bring the whole AI Gateway stack up in Docker and LEAVE IT RUNNING, so you can
# use the control plane, the LiteLLM proxy, and the admin UI interactively.
#
# This is the long-running counterpart to scripts/e2e_docker_qa.sh: that script
# is a CI gate that asserts and then tears the stack down; this one starts the
# stack detached and prints how to reach it. Stop it with `make docker-down`.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f deploy/docker-compose/docker-compose.yml)

echo "==> Building images and starting the full stack (detached)"
"${COMPOSE[@]}" up -d --build

echo "==> Waiting for governance-api and the LiteLLM proxy to become healthy"
wait_ok() { # <name> <url> <service>
  for _ in $(seq 1 120); do
    curl -sf "$2" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "WARN: $1 did not become healthy in time; check: ${COMPOSE[*]} logs $3"
  return 1
}
wait_ok "governance-api" "http://localhost:8080/healthz" governance-api || true
wait_ok "litellm-proxy" "http://localhost:4000/health/liveliness" litellm-proxy || true

# The one-shot seed container prints a fresh virtual key; surface it for testing.
KEY=$("${COMPOSE[@]}" logs --no-color seed 2>/dev/null | grep -oE 'sk-ag-[A-Za-z0-9_-]+' | head -1 || true)

echo ""
echo "AI Gateway is up and running:"
echo ""
echo "  Control plane (governance API)     http://localhost:8080     (/docs for Swagger UI)"
echo "  LiteLLM proxy (OpenAI-compatible)  http://localhost:4000"
echo "  Admin UI                           http://localhost:8081"
echo "  Stub provider (fake upstream)      http://localhost:9099"
echo ""
echo "Seeded virtual key: ${KEY:-<run: ${COMPOSE[*]} logs seed>}"
echo ""
echo "Example request through the proxy:"
echo "  curl -s localhost:4000/v1/chat/completions \\"
echo "    -H 'Authorization: Bearer ${KEY:-<KEY>}' -H 'Content-Type: application/json' \\"
echo "    -d '{\"model\":\"demo-gpt\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'"
echo ""
echo "Manage the stack:  make docker-logs   |   make docker-ps   |   make docker-down"
