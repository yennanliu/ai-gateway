# AI Gateway

An enterprise LLM gateway built on top of [LiteLLM Proxy](https://docs.litellm.ai/docs/simple_proxy):
one OpenAI-compatible API in front of many providers, with governance, virtual keys,
budgets, usage/cost tracking, guardrails, and audit — self-hostable for the on-prem /
private-cloud / compliance story.

See [`doc/system-design.md`](doc/system-design.md), [`doc/implementation-plan.md`](doc/implementation-plan.md),
and [`doc/deployment-and-gtm.md`](doc/deployment-and-gtm.md).

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

Open http://localhost:5173 and sign in with the dev principal (user `admin`,
the org id printed by `make seed`, roles `org-admin`).

Test / lint:

```bash
make test            # pytest (+ coverage) and vitest
make lint            # ruff + mypy
./scripts/smoke.sh   # end-to-end: migrate -> seed -> API -> authenticated request
```

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
