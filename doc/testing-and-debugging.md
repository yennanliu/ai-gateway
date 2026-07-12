# Testing & Debugging

How to verify the system works and how to debug it locally. Everything runs
with no external services (SQLite, in-process cache, bundled stub provider).

## 1. Test layers

| Layer | Command | What it covers |
|---|---|---|
| Unit + API (in-process) | `make test-py` / `uv run pytest` | Domain logic + FastAPI routes on in-memory SQLite (fast) |
| UI | `make test-ui` / `cd admin-ui && npm run test:unit` | Vue stores, client, components (vitest) |
| Integration (LiteLLM) | `uv run pytest tests/integration` | Real `litellm.Router` routing + fallback vs a stub provider |
| **E2E (real server)** | `make e2e` / `uv run pytest tests/e2e` | Boots uvicorn as a subprocess, drives the full governance lifecycle over HTTP |
| **Full system (docker compose)** | `make e2e-docker` / `./scripts/e2e_docker.sh` | Real LiteLLM proxy + control plane + stub provider in containers; a real `/v1/chat/completions` through custom-auth + routing, plus a 401 for an unknown key |
| Smoke (shell) | `make smoke` / `./scripts/smoke.sh` | Clean DB → migrate → seed → API → authenticated request |
| Lint / types | `make lint` | ruff + mypy (strict) |

`make test` runs unit + UI. `make e2e` and `make e2e-docker` are separate (they start real processes/containers, so they're slower). CI runs all of them (`backend`, `migrations-postgres`, `e2e`, `full-system`, `ui` jobs).

## 2. Interactive API docs (Swagger / OpenAPI)

With the API running (`make api`):

- **Swagger UI:** http://localhost:8080/docs — try endpoints in the browser.
- **ReDoc:** http://localhost:8080/redoc
- **Raw schema:** http://localhost:8080/openapi.json
- Export the schema to a file: `make openapi` → `openapi.json`.

In Swagger, use the endpoints with the dev auth headers (see below) — click an
endpoint, "Try it out", and add the `X-User-Id` / `X-Org-Id` / `X-Org-Roles` headers.

## 3. Manual testing with curl (dev auth)

The control plane uses a dev header shim until OIDC lands. Every call needs:

```
-H "X-User-Id: <anything>" -H "X-Org-Id: <org>" -H "X-Org-Roles: org-admin"
```

Full flow against a running API (`make api` on :8080):

```bash
# create an org (platform admin: org-admin role, no org id needed)
ORG=$(curl -s -XPOST localhost:8080/api/v1/orgs \
  -H "X-User-Id: me" -H "X-Org-Roles: org-admin" \
  -H "Content-Type: application/json" -d '{"name":"Acme"}' | jq -r .id)

# as org-admin of that org
H=(-H "X-User-Id: me" -H "X-Org-Id: $ORG" -H "X-Org-Roles: org-admin" -H "Content-Type: application/json")

TEAM=$(curl -s -XPOST localhost:8080/api/v1/teams "${H[@]}" -d "{\"org_id\":\"$ORG\",\"name\":\"Core\"}" | jq -r .id)
curl -s -XPOST localhost:8080/api/v1/models "${H[@]}" -d '{"public_name":"gpt","provider":"openai","model":"gpt-4o"}'
curl -s -XPOST localhost:8080/api/v1/keys "${H[@]}" -d "{\"team_id\":\"$TEAM\"}"   # returns plaintext key once
curl -s localhost:8080/api/v1/usage "${H[@]}"
```

Or just run `make seed` — it prints an org id and a ready-to-use virtual key.

## 4. Do I need to run the LiteLLM proxy locally?

**Not for most work.** `make dev` runs the **control plane + UI + a stub provider**
(migrations, seed, governance-api :8080, Vue :5173, stub :9099). The **LiteLLM
proxy itself (the data plane) is not required** to develop or test the API, the
UI, budgets, guardrails logic, billing, or to run unit/e2e tests — those don't
route real inference.

`make dev` starts the proxy **only if the `litellm[proxy]` extra is installed**
(it probes for it and skips otherwise, so the default dev loop stays light).

You **do** need the proxy running to exercise the real inference path
(`/v1/chat/completions` → custom-auth → routing/fallback → metering). Easiest —
one click, no host setup, via Docker Compose:

```bash
make e2e-docker    # docker compose up (seeded + wired) + a real request through LiteLLM
```

Or bare-metal:

```bash
make proxy    # installs litellm[proxy] and runs the proxy on :4000
```

Then (with `make api` + `make seed` already run, and the stub provider up) use
the virtual key printed by `make seed`:

```bash
uv run python scripts/stub_provider.py &   # fake provider on :9099 (if not already up)
curl -s localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer <KEY>" -H "Content-Type: application/json" \
  -d '{"model":"demo-gpt","messages":[{"role":"user","content":"hi"}]}'
```

An unknown/expired/revoked key returns 401 (custom-auth); a successful call is
metered into `usage_records`. Note: routing + fallback are also verified without
a running proxy by the integration test (`uv run pytest tests/integration`),
which drives a real `litellm.Router` against the stub.

## 5. Inspecting local state

```bash
# tables + row counts
uv run python - <<'PY'
import sqlite3
c = sqlite3.connect("ai-gateway.db")
for (t,) in c.execute("select name from sqlite_master where type='table' order by name"):
    n = c.execute(f"select count(*) from {t}").fetchone()[0]
    print(f"{t:24} {n}")
PY

# view the compiled proxy config
cat litellm.config.yaml
```

Reset everything: `make clean && make migrate && make seed`.

## 6. Common issues

| Symptom | Cause / fix |
|---|---|
| `401 unauthenticated` | Missing `X-User-Id` header. Add the dev auth headers (§3). |
| `403 insufficient permissions` | Principal lacks the role for that org/team. Use `X-Org-Roles: org-admin` and the matching `X-Org-Id`. |
| `400 no org context` | Config/billing endpoints need `X-Org-Id` set. |
| `404` on a model/team | Wrong id, or it belongs to another org (tenant scoping). |
| UI shows no data | Start the backend first — the Vite dev server proxies `/api` → `:8080`. |
| `pnpm: command not found` | Makefile falls back to `npm`, or run `corepack enable`. |
| e2e can't start server | Ensure `uv sync --all-packages` ran; check the port isn't taken. |

## 7. Debugging tips

- **Verbose API logs:** run `uv run uvicorn governance_api.main:app --reload --log-level debug`.
- **Single test:** `uv run pytest -k <name> -v` (add `-s` to see prints).
- **Coverage gaps:** `make test-py` prints missing lines per file.
- **Reproduce CI's Postgres path:** set `AIGW_DATABASE_URL=postgresql+psycopg://…` and `uv run alembic … upgrade head` (needs `--extra postgres`).
