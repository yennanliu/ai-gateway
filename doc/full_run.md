# Full Run (control plane + data plane)

`make dev` gives you the control plane + UI + a stub provider — enough for almost
all work, with no real inference. This doc is for the other case: you want the
**full stack running end-to-end**, including the LiteLLM proxy (data plane), so
you can actually send a `/v1/chat/completions` call through routing → custom-auth
→ metering.

See also: [testing & debugging](testing-and-debugging.md#4-do-i-need-to-run-the-litellm-proxy-locally)
for the background on why the proxy is optional, and [system design](system-design.md)
for the two-plane architecture.

## Option A: Docker Compose (no host setup)

Everything runs in containers via `deploy/docker-compose/docker-compose.yml` — no
host Python/uv, no manual seeding. It builds the control-plane and data-plane
images, brings up a stub upstream provider, seeds demo data, compiles the LiteLLM
config onto a shared volume, then starts the proxy already wired to serve real
(stubbed) inference. Pick the mode you want:

- **A1 — run it as a service** you can click around and send requests to → `make docker-up`
- **A2 — run it as a one-shot test** that verifies the system and cleans up → `make e2e-docker`

**Prerequisite (both):** a running Docker engine (Docker Desktop, or `colima start`).

### A1. Run it as a service you can use — `make docker-up`

Use this when you want the whole system up and **staying up**, so you can use the
admin UI, try Swagger, and send real inference through the proxy.

```bash
make docker-up
```

This builds + starts everything detached, waits for the control plane and proxy
to become healthy, and prints the URLs plus the seeded virtual key. You get:

| URL | What |
|---|---|
| http://localhost:8080 | Control plane (governance API); Swagger UI at `/docs` |
| http://localhost:4000 | LiteLLM proxy (OpenAI-compatible inference) |
| http://localhost:8081 | Admin UI |
| http://localhost:9099 | Stub upstream provider (fake OpenAI) |

Send a chat completion through the proxy with the printed `sk-ag-…` key:

```bash
curl -s localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer <KEY>" -H "Content-Type: application/json" \
  -d '{"model":"demo-gpt","messages":[{"role":"user","content":"hi"}]}'
```

Manage the running stack:

```bash
make docker-ps      # container status
make docker-logs    # tail logs (Ctrl-C to stop tailing)
make docker-down    # stop + remove containers and the data volume
```

(Lost the key? `docker compose -f deploy/docker-compose/docker-compose.yml logs seed`.)

### A2. Run it as a one-shot test — `make e2e-docker`

Use this to verify the whole system works end-to-end. It brings the **same** stack
up, runs ~34 assertions across both planes (health/version, auth 401, RBAC 403,
model registry, real chat completions, the issue→use→revoke→reject key lifecycle,
billing), then **tears the stack down**. It's the CI `full-system` job, so it must
clean up after itself — it is *not* a way to keep the app running (use A1 for that).

```bash
make e2e-docker         # comprehensive QA (scripts/e2e_docker_qa.sh)
make e2e-docker-smoke   # fast variant: one real completion + a 401
```

See [testing & debugging §4.1](testing-and-debugging.md#41-running-the-full-system-docker-e2e-qa-locally)
for the full assertion list and what to expect.

## Option B: bare-metal (hot-reload dev loop)

Better for iterating on the control plane or hooks with fast reload.

### 1. Install deps (once)

```bash
uv sync --all-packages          # control plane + hooks package
cd admin-ui && npm install      # UI deps
cd ..
```

### 2. Prepare the DB

```bash
make migrate                    # create local SQLite schema
make seed                       # demo org/team/model/key; prints a virtual key + org id
```

### 3. Start every piece

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

### 4. Exercise the real inference path

Using the virtual key printed by `make seed`:

```bash
curl -s localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer <KEY>" -H "Content-Type: application/json" \
  -d '{"model":"demo-gpt","messages":[{"role":"user","content":"hi"}]}'
```

- An unknown/expired/revoked key returns 401 (custom-auth).
- A successful call is metered into `usage_records` — check via
  `curl -s localhost:8080/api/v1/usage "${H[@]}"` (see the header shim below).

### 5. Control-plane calls need dev auth headers

There's no OIDC yet; every control-plane request needs:

```
-H "X-User-Id: <anything>" -H "X-Org-Id: <org>" -H "X-Org-Roles: org-admin"
```

The UI injects these automatically after dev sign-in. For curl flows, see
[testing & debugging §3](testing-and-debugging.md#3-manual-testing-with-curl-dev-auth).

### 6. Everything running — the checklist

| Port | Process | Command |
|---|---|---|
| :9099 | Stub LLM provider | `uv run python scripts/stub_provider.py` |
| :8080 | Governance API (control plane) | `make api` |
| :5173 | Vue UI | `make ui` |
| :4000 | LiteLLM proxy (data plane) | `make proxy` |

Test / lint the whole thing:

```bash
make test            # unit: pytest (+ coverage) and vitest
uv run pytest tests/integration   # real litellm.Router + the control<->data-plane seams vs the stub
make e2e             # end-to-end: boots the real server, drives the API over HTTP
make e2e-docker      # full-system QA: docker compose up + ~34 assertions across both planes, then teardown
make lint            # ruff + mypy
make smoke           # shell smoke: migrate -> seed -> API -> authenticated request
```

Reset everything: `make clean && make migrate && make seed`. To just run the
whole system in Docker and leave it up, see [Option A1](#a1-run-it-as-a-service-you-can-use--make-docker-up).

## LiteLLM's own Admin UI (`/ui`) — not wired up, by design

LiteLLM ships an Admin UI at `/ui` on the proxy port, but it **requires
LiteLLM's own database** (`DATABASE_URL`, and its bundled Prisma schema is
hardcoded to `provider = "postgresql"`) — even the username/password login flow
calls into it to mint a session key. That's exactly the dependency this project
avoids: per `CLAUDE.md`, **our own DB is the source of truth for virtual keys
and spend, not LiteLLM's Prisma/Postgres key store.** Standing up a Postgres
instance just to unlock `/ui` would reintroduce a second, parallel key/session
store that the rest of the system doesn't know about.

So there's no username/password to give you here — the Admin UI is
intentionally left unconfigured. Manage everything (orgs, teams, keys, models,
budgets) through our own control plane instead:

- **Our admin-ui** (`make ui`, or `admin-ui` in docker compose) — the real UI for this product.
- **Swagger** at `http://localhost:8080/docs` — try any control-plane endpoint directly.

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
- **`scripts/e2e_docker.sh` fails to reach the stub provider** — the stub binds
  `AIGW_STUB_HOST` (default `127.0.0.1`, `0.0.0.0` in docker compose so other
  containers can reach it); if you copy the compose file, keep that override.
- **Reset local state** — `make clean` removes the SQLite DB and caches; then
  `make migrate && make seed`. For docker compose: `docker compose -f deploy/docker-compose/docker-compose.yml down -v`.
