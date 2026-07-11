# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An enterprise LLM gateway built **on top of** LiteLLM Proxy. The architecture is a
deliberate two-plane split (see `doc/system-design.md`, the authoritative spec):

- **Data plane** = LiteLLM Proxy, consumed as a **pinned dependency** (never forked).
  It owns the OpenAI-compatible `/v1/*` surface, provider adapters, routing, and
  fallback. We extend it **only** through four documented seams: custom-auth callable,
  callback/`CustomLogger`, config schema, and the OpenAI wire shape.
- **Control plane** = our FastAPI service (`governance-api`) — orgs/teams/users/keys,
  model registry, budgets, usage/billing, RBAC, audit. This is the product.

The single most important invariant: **our SQLite/Postgres DB is the source of truth
for virtual keys and spend, not LiteLLM's Prisma/Postgres key store.** LiteLLM
authenticates every request by calling *back* into our DB via the custom-auth hook.
This is what keeps SQLite viable end-to-end. Don't reintroduce a dependency on
LiteLLM's own key/spend tables.

## Monorepo layout (uv workspace)

Root `pyproject.toml` is the uv workspace; the single `uv.lock` pins everything
(including LiteLLM). Three deployable pieces:

| Path | Python package / app | Role |
|---|---|---|
| `control-plane/governance-api/` | `governance_api` | The FastAPI control plane |
| `data-plane/hooks/` | `aigw-hooks` (module `hooks`) | LiteLLM extension package, loaded in-proc by the proxy |
| `admin-ui/` | Vue 3 + Vite + TS + Pinia | All UI (admin console + self-serve) |

Note the coupling direction: `aigw-hooks` **depends on** `governance-api` (the hooks
import `governance_api.services.metering`, `governance_api.db`, etc.) so the proxy
process shares our DB models. The reverse is never true — the control plane must not
import `hooks`.

## Commands

```bash
make dev        # migrate + seed + stub provider (:9099) + governance-api (:8080) + Vue (:5173)
make api        # backend only (uvicorn, hot reload, :8080)
make ui         # frontend only (Vite, :5173) — proxies /api -> :8080
make test       # test-py + test-ui
make e2e        # boots the REAL server over HTTP and drives the API (tests/e2e)
make lint       # ruff check + mypy (strict)
make format     # ruff format + ruff check --fix
make migrate    # alembic upgrade head
make revision m="msg"   # autogenerate a migration
make seed       # demo org/team/model/key — prints a virtual key
make proxy      # install litellm[proxy] extra + run the LiteLLM data plane on :4000
make smoke      # shell smoke: migrate -> seed -> API -> authenticated request
make openapi    # export OpenAPI schema
make clean      # rm SQLite db + caches
```

Run a single Python test (pytest `testpaths` are preconfigured, so paths are relative to root):

```bash
uv run pytest control-plane/governance-api/tests/test_keys_api.py::test_issue_key -q
uv run pytest -k rate_limit          # by keyword across all suites
```

Single UI test: `cd admin-ui && npm run test:unit -- KeysView`.

**The LiteLLM proxy is optional for almost all work.** `make dev` starts it only if
the `proxy` extra is installed; the control plane, UI, and unit/e2e tests never route
real inference. Only run `make proxy` when you specifically need to exercise
`/v1/chat/completions` through LiteLLM. See
`doc/testing-and-debugging.md`.

## Conventions that span files

**Auth (dev shim).** There is no OIDC yet. Requests are authenticated via headers
resolved in `auth/dependencies.py` into a `Principal` (`auth/principal.py`):
`X-User-Id` (required), `X-Org-Id`, `X-Org-Roles` (comma-separated, e.g. `org-admin`),
`X-Team-Roles` (`team_id:role,...`). RBAC lives in `auth/authz.py` — **org-admin of the
owning org is a superset of every team-level permission in that org.** When SSO lands,
only `get_principal` changes; route code depends solely on the `Principal` shape.

**RBAC roles** (constants in `auth/principal.py`): `org-admin`, `team-admin`,
`developer`, `billing-viewer`, `auditor`.

**Scope resolution** (`domain/scoping.py`). Budgets and policies attach at any level
and resolve **most-specific-wins**: `key > app > user > team > org`
(`SCOPE_PRECEDENCE`). This ordering *is* the precedence rule; `domain/` holds pure,
DB-free logic tested to ~100%.

**API routers.** One router per resource under `api/`, all prefixed `/api/v1`, wired in
`main.py::create_app`. Use the shared helpers in `api/deps.py`: `SessionDep`,
`PrincipalDep`, `get_or_404`, `flush_or_409` (maps `IntegrityError` -> 409). Request/
response models are Pydantic in `api/schemas.py`. Mutating endpoints call
`services.audit.record(...)` to append an `AuditEvent` (append-only; never updated/deleted).

**Virtual keys.** Only the hash + a display `prefix` are stored. Plaintext is returned
**exactly once**, on issue and rotate (`security/keys.py`, `api/keys.py`). The same
hash function (`hash_key`) is used by the data-plane custom-auth in `hooks/auth.py`.

**DB layer.** Sync SQLAlchemy 2.0 (the control plane is not the hot path). SQLite is
the default; **swap to Postgres by changing `AIGW_DATABASE_URL` only** — same models and
migrations. `db/session.py` enables SQLite FK enforcement via a `PRAGMA foreign_keys=ON`
connect hook so `ON DELETE CASCADE` behaves like Postgres; keep this in mind when adding
relationships. Array/`jsonb` fields map to JSON columns on SQLite. Alembic config is
`control-plane/governance-api/alembic.ini` (the Makefile always points `-c` at it).

**Config compiler** (`services/config_compiler.py`). The registry (DB) is source of
truth; the LiteLLM YAML is a **derived artifact** — never hand-edit prod YAML. Secrets
are emitted as `os.environ/<ref>` references, so the written config never contains
plaintext credentials. `compile_for_org` -> `write_config` renders it.

**LiteLLM version pin.** `COMPATIBLE_LITELLM` in `config.py` is the exact tested
version, surfaced at `GET /api/v1/version`. When bumping LiteLLM, update this and verify
the four seams (`hooks/auth.py`, `hooks/callbacks.py`, the config schema, wire shape).

**UI.** Typed client in `admin-ui/src/api/client.ts` (mirrors the control-plane API;
`setAuthHeadersProvider` lets the auth store inject dev headers). Vite dev server
proxies `/api` -> `:8080`, so start the backend first for live data. State is Pinia
stores in `src/stores/`.

## Testing & style

- **TDD is the working style**; tests live next to the code (`tests/` per package plus
  root `tests/{e2e,integration,load}`). Unit tests run hermetically on **in-memory
  SQLite** — no external services (`conftest.py` gives `db`, `app`, `client`,
  `as_principal` fixtures; override principals via `app.dependency_overrides`).
- `make lint` = `ruff check` (line length 100; rules `E,F,I,UP,B,SIM`; migrations
  excluded) + `mypy` in **strict** mode over `control-plane/governance-api/src` only.
- Every production dependency (Postgres, Redis, Vault, OTel) has a zero-config local
  fallback (SQLite, in-process cache, `.env`, no-op). Preserve this local-first
  property — don't make the inner loop require a real service.

## Deploy

`deploy/docker-compose/` (on-prem; `--profile scale` adds Postgres + Redis) and
`deploy/helm/ai-gateway/` (k8s; proxy autoscales via HPA). Operations in `doc/runbook.md`.
