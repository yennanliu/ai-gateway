# AI Gateway

An enterprise LLM gateway built on top of [LiteLLM Proxy](https://docs.litellm.ai/docs/simple_proxy):
one OpenAI-compatible API in front of many providers, with governance, virtual keys,
budgets, usage/cost tracking, guardrails, and audit — self-hostable for the on-prem /
private-cloud / compliance story.

Docs: [system design](doc/system-design.md) · [implementation plan](doc/implementation-plan.md) ·
[deployment & GTM](doc/deployment-and-gtm.md) · [testing & debugging](doc/testing-and-debugging.md) ·
[runbook](doc/runbook.md).

## Stack

- **Backend:** Python + FastAPI, managed with [uv]; SQLAlchemy + Alembic.
- **Datastore:** SQLite by default (zero-ops local/on-prem); Postgres by connection-string swap.
- **Frontend:** Vue 3 + Vite + TypeScript + Pinia (all UI).
- **Data plane:** LiteLLM Proxy (pinned; see `/api/v1/version`), extended via our custom-auth + callback hooks.
- **Testing:** pytest (backend) + vitest (UI); TDD; local-first — no external services required.

## Quickstart

Prerequisites: [uv], Node 20+. No external services needed — SQLite file,
in-process cache, and a bundled stub provider mean no real API keys are required.

```bash
uv sync --all-packages          # install Python deps
make migrate                    # create local SQLite schema
make seed                       # demo org/team/model/key (prints a virtual key)
cd admin-ui && npm install      # install UI deps
```

Run the dev stack — migrates, seeds, then starts the stub provider (:9099),
governance-api (:8080), and the Vue UI (:5173), all hot-reloading:

```bash
make dev
```

`make dev` does **not** require the LiteLLM proxy (data plane) — the control
plane, UI, and tests don't route real inference. It starts the proxy only if the
`litellm[proxy]` extra is installed; run `make proxy` to install and run it on
:4000 when you want to test actual `/v1/chat/completions` calls. See
[testing & debugging](doc/testing-and-debugging.md#4-do-i-need-to-run-the-litellm-proxy-locally).

Open http://localhost:5173 and sign in with the dev principal (user `admin`,
the org id printed by `make seed`, roles `org-admin`).

### Running backend and frontend separately

`make dev` runs everything together; you can also run each side on its own
(handy when you only touch one, or want separate log streams):

```bash
make api    # backend only — governance-api on :8080 (hot reload)
make ui     # frontend only — Vue dev server on :5173 (hot reload)
```

Notes:
- Run `make migrate && make seed` once before `make api` so the DB exists and
  has demo data.
- The Vue dev server proxies `/api` → `http://localhost:8080`, so **start the
  backend before the UI** if you want live data (the UI still loads without it —
  requests just fail until the backend is up).
- Optional: the stub LLM provider (only needed for actual model calls through
  the proxy) runs on its own:

  ```bash
  uv run python scripts/stub_provider.py   # :9099
  ```

Test / lint:

```bash
make test            # unit: pytest (+ coverage) and vitest
make e2e             # end-to-end: boots the real server, drives the API over HTTP
make lint            # ruff + mypy
make smoke           # shell smoke: migrate -> seed -> API -> authenticated request
```

**API docs (Swagger):** with the backend running, open http://localhost:8080/docs
(Swagger UI), `/redoc`, or `/openapi.json`. `make openapi` exports the schema.
See [testing & debugging](doc/testing-and-debugging.md) for manual curl flows,
data-plane testing, and troubleshooting.

### Troubleshooting

- **401 from the API** — control-plane calls need dev auth headers
  (`X-User-Id`, `X-Org-Id`, `X-Org-Roles`); the UI sends them after dev sign-in.
- **`pnpm: command not found`** — the Makefile falls back to `npm`, or run
  `corepack enable`.
- **Reset local state** — `make clean` removes the SQLite DB and caches; then
  `make migrate && make seed`.

## Status

Building per the [implementation plan](doc/implementation-plan.md), test-first:

- [x] **M0** — Bootstrap & CI (workspace, FastAPI `/healthz`, test harness, Vue scaffold, CI)
- [x] **M1** — Data model & migrations (13 entities, cascades, scope resolution, Alembic)
- [x] **M2** — Governance API & RBAC (org/team/user/membership/app CRUD, virtual-key lifecycle, RBAC, audit)
- [x] **M3** — LiteLLM integration & config compiler (custom-auth, compile→write→reload, real-LiteLLM routing/fallback test)
- [x] **M4** — Metering, budgets, rate limits & guardrails
- [x] **M5** — Usage aggregation & billing (aggregation, invoices, CSV export, budget alerts, rate cards)
- [x] **M6** — Vue admin UI (typed client, auth store, models/keys/usage/budgets views + stores)
- [x] **M7** — Local DX polish (make seed, stub provider, make dev, smoke script, quickstart)
- [x] **M8** — Deploy & hardening (Dockerfiles, Compose SQLite/Postgres profiles, Helm chart + HPA, load test, [runbook](doc/runbook.md))

## Deploy

- **Compose (on-prem):** `cd deploy/docker-compose && docker compose up --build`
  (add `--profile scale` for Postgres + Redis).
- **Kubernetes:** `helm upgrade --install ai-gateway deploy/helm/ai-gateway ...`
  (proxy autoscales via HPA).
- Operations, upgrades, secrets, scaling, and incident response: [`doc/runbook.md`](doc/runbook.md).

[uv]: https://docs.astral.sh/uv/
