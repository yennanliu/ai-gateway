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

# LiteLLM resolves custom_auth as a .py file next to --config and execs it
# without registering it in sys.modules, which crashes on our frozen dataclass
# + `from __future__ import annotations`. Regenerate a shim there every start
# (repo root locally, the shared /data volume in docker-compose) that just
# re-imports the real module through the normal import system instead.
CONFIG_DIR="$(cd "$(dirname "$CONFIG")" && pwd)"
mkdir -p "$CONFIG_DIR/hooks"
cat > "$CONFIG_DIR/hooks/auth.py" <<'PY'
import os
import sys

# The proxy execs this file directly (see entrypoint.sh above); make sure `hooks`
# resolves to the installed aigw-hooks package and never this shim's own dir,
# even if CONFIG_DIR is on sys.path -- otherwise `hooks` binds to this file as a
# namespace package and the import below re-imports itself (circular import).
_shim_dir = os.path.dirname(os.path.abspath(__file__))
_config_dir = os.path.dirname(_shim_dir)
_saved_path = sys.path[:]
try:
    sys.path = [p for p in sys.path if os.path.abspath(p or ".") not in (_shim_dir, _config_dir)]
    from hooks.auth import user_api_key_auth  # noqa: F401
finally:
    sys.path = _saved_path
PY

echo "==> Starting LiteLLM proxy on :$PORT with config $CONFIG"
exec litellm --config "$CONFIG" --port "$PORT"
