#!/usr/bin/env bash
# Full-system e2e: `docker compose up` a real LiteLLM proxy + governance-api +
# a stub provider (see deploy/docker-compose/docker-compose.yml), then drive a
# real /v1/chat/completions call through custom-auth -> routing -> the stub.
# Proves the two planes work together, not just in isolation. Always tears the
# stack back down on exit. Run: ./scripts/e2e_docker.sh
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f deploy/docker-compose/docker-compose.yml)
CHAT_OUT="$(mktemp)"
cleanup() {
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$CHAT_OUT"
}
trap cleanup EXIT

echo "==> Building and starting stub-provider, governance-api, seed, litellm-proxy"
"${COMPOSE[@]}" up -d --build stub-provider governance-api seed litellm-proxy

echo "==> Waiting for the LiteLLM proxy to become healthy (seed runs first)"
ok=""
for _ in $(seq 1 90); do
  if curl -sf localhost:4000/health/liveliness >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [ -z "$ok" ]; then
  echo "FAIL: proxy never became healthy"
  "${COMPOSE[@]}" logs
  exit 1
fi

echo "==> Extracting the seeded virtual key"
KEY=$("${COMPOSE[@]}" logs --no-color seed | grep -oE 'sk-ag-[A-Za-z0-9_-]+' | head -1 || true)
if [ -z "$KEY" ]; then
  echo "FAIL: no virtual key found in seed logs"
  "${COMPOSE[@]}" logs seed
  exit 1
fi

echo "==> Authenticated chat completion through the real proxy"
CODE=$(curl -s -o "$CHAT_OUT" -w "%{http_code}" localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"demo-gpt","messages":[{"role":"user","content":"hi"}]}' || echo "000")
if [ "$CODE" = "200" ] && grep -q "Hello from the AI Gateway stub" "$CHAT_OUT"; then
  echo "OK: chat completion routed through custom-auth + LiteLLM"
else
  echo "FAIL: chat completion returned $CODE"
  cat "$CHAT_OUT"
  exit 1
fi

echo "==> Unknown key is rejected"
CODE=$(curl -s -o /dev/null -w "%{http_code}" localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-ag-bogus" -H "Content-Type: application/json" \
  -d '{"model":"demo-gpt","messages":[{"role":"user","content":"hi"}]}' || echo "000")
if [ "$CODE" = "401" ]; then
  echo "OK: unknown key rejected (401)"
else
  echo "FAIL: expected 401 for an unknown key, got $CODE"
  exit 1
fi

echo "FULL-SYSTEM E2E PASSED"
