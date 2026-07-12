# Full Run (control plane + data plane)

`make dev` gives you the control plane + UI + a stub provider — enough for almost
all work, with no real inference. This doc is for the other case: you want the
**full stack running end-to-end**, including the LiteLLM proxy (data plane), so
you can actually send a `/v1/chat/completions` call through routing → custom-auth
→ metering.

See also: [testing & debugging](testing-and-debugging.md#4-do-i-need-to-run-the-litellm-proxy-locally)
for the background on why the proxy is optional, and [system design](system-design.md)
for the two-plane architecture.

## 1. Install deps (once)

```bash
uv sync --all-packages          # control plane + hooks package
cd admin-ui && npm install      # UI deps
cd ..
```

## 2. Prepare the DB

```bash
make migrate                    # create local SQLite schema
make seed                       # demo org/team/model/key; prints a virtual key + org id
```

## 3. Start every piece

Run each in its own terminal (or background with `&`):

```bash
uv run python scripts/stub_provider.py &   # fake upstream provider on :9099
make api &                                 # governance-api (control plane) on :8080
make ui &                                  # Vue UI on :5173 (proxies /api -> :8080)
make proxy                                 # installs litellm[proxy] extra, runs LiteLLM (data plane) on :4000
```

`make proxy` is the piece `make dev` skips by default — it installs the
`litellm[proxy]` extra and runs `data-plane/litellm/entrypoint.sh`, which starts
`litellm --config litellm.config.yaml --port 4000` wired to our custom-auth hook
(`hooks.auth.user_api_key_auth`). Once the extra is installed, subsequent
`make dev` runs will auto-detect it and start the proxy too.

If `litellm.config.yaml` doesn't exist yet, the entrypoint falls back to
`data-plane/litellm/config.template.yaml`. The real config is a **derived
artifact** compiled from the DB registry (`services/config_compiler.py`) —
never hand-edit it.

## 4. Exercise the real inference path

Using the virtual key printed by `make seed`:

```bash
curl -s localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer <KEY>" -H "Content-Type: application/json" \
  -d '{"model":"demo-gpt","messages":[{"role":"user","content":"hi"}]}'
```

- An unknown/expired/revoked key returns 401 (custom-auth).
- A successful call is metered into `usage_records` — check via
  `curl -s localhost:8080/api/v1/usage "${H[@]}"` (see the header shim below).

## 5. Control-plane calls need dev auth headers

There's no OIDC yet; every control-plane request needs:

```
-H "X-User-Id: <anything>" -H "X-Org-Id: <org>" -H "X-Org-Roles: org-admin"
```

The UI injects these automatically after dev sign-in. For curl flows, see
[testing & debugging §3](testing-and-debugging.md#3-manual-testing-with-curl-dev-auth).

## 6. Everything running — the checklist

| Port | Process | Command |
|---|---|---|
| :9099 | Stub LLM provider | `uv run python scripts/stub_provider.py` |
| :8080 | Governance API (control plane) | `make api` |
| :5173 | Vue UI | `make ui` |
| :4000 | LiteLLM proxy (data plane) | `make proxy` |

Test / lint the whole thing:

```bash
make test            # unit: pytest (+ coverage) and vitest
uv run pytest tests/integration   # real litellm.Router vs the stub, no proxy process needed
make e2e             # end-to-end: boots the real server, drives the API over HTTP
make lint            # ruff + mypy
make smoke           # shell smoke: migrate -> seed -> API -> authenticated request
```

Reset everything: `make clean && make migrate && make seed`.

## Troubleshooting

- **401 from the data plane** — the key is unknown/expired/revoked, or the
  proxy's custom-auth can't reach the control-plane DB.
- **401 from the control-plane API** — missing `X-User-Id` / `X-Org-Id` /
  `X-Org-Roles` headers.
- **`make proxy` fails to install** — it needs the `litellm[proxy]` extra;
  make sure `uv sync --all-packages --extra proxy` succeeds on its own first.
- **Proxy can't find a model** — check `cat litellm.config.yaml` was compiled
  after `make seed` created the demo model; recompile via the config API or
  rerun seed.
- **Reset local state** — `make clean` removes the SQLite DB and caches; then
  `make migrate && make seed`.
