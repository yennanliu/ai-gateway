#!/usr/bin/env bash
# Start the LiteLLM proxy with our custom-auth hook.
# Requires the `aigw-hooks` package (installs `hooks`) and litellm[proxy] on PATH.
# The custom_auth path in the config resolves to hooks.auth.user_api_key_auth.
set -euo pipefail

CONFIG="${AIGW_LITELLM_CONFIG:-./litellm.config.yaml}"
PORT="${AIGW_PROXY_PORT:-4000}"

if [ ! -f "$CONFIG" ]; then
  echo "==> No compiled config at $CONFIG; using base template"
  CONFIG="$(dirname "$0")/config.template.yaml"
fi

echo "==> Starting LiteLLM proxy on :$PORT with config $CONFIG"
exec litellm --config "$CONFIG" --port "$PORT"
