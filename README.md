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

Prerequisites: [uv], Node 20+.

```bash
uv sync --all-packages          # install Python deps
make migrate                    # create local SQLite schema
cd admin-ui && npm install      # install UI deps
```

Run the dev stack (governance-api on :8080, Vue on :5173):

```bash
make dev
```

Test / lint:

```bash
make test        # pytest (+ coverage) and vitest
make lint        # ruff + mypy
```

## Status

Building per the [implementation plan](doc/implementation-plan.md), test-first:

- [x] **M0** — Bootstrap & CI (workspace, FastAPI `/healthz`, test harness, Vue scaffold, CI)
- [x] **M1** — Data model & migrations (13 entities, cascades, scope resolution, Alembic)
- [x] **M2** — Governance API & RBAC (org/team/user/membership/app CRUD, virtual-key lifecycle, RBAC, audit)
- [x] **M3** — LiteLLM integration & config compiler (custom-auth, compile→write→reload, real-LiteLLM routing/fallback test)
- [x] **M4** — Metering, budgets, rate limits & guardrails
- [ ] M5 — Usage aggregation & billing
- [ ] M6 — Vue admin UI
- [ ] M7 — Local DX polish
- [ ] M8 — Deploy & hardening

[uv]: https://docs.astral.sh/uv/
