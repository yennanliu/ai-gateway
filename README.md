# AI Gateway

An enterprise LLM gateway built on top of [LiteLLM Proxy](https://docs.litellm.ai/docs/simple_proxy):
one OpenAI-compatible API in front of many providers, with governance, virtual keys,
budgets, usage/cost tracking, guardrails, and audit — self-hostable for the on-prem /
private-cloud / compliance story.

Docs: [system design](doc/system-design.md) · [implementation plan](doc/implementation-plan.md) ·
[deployment & GTM](doc/deployment-and-gtm.md) · [testing & debugging](doc/testing-and-debugging.md) ·
[full run](doc/full_run.md) · [runbook](doc/runbook.md).

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

### Full run (with the data plane)

Everything above skips the LiteLLM proxy (data plane) by default. To run the
**full stack** — stub provider + governance-api + UI + LiteLLM proxy — and
actually exercise `/v1/chat/completions`, one click via Docker Compose:

```bash
make docker-up       # build + start the whole stack, detached, and LEAVE IT RUNNING
                     # control :8080 · proxy :4000 · admin-ui :8081 · stub :9099 · prints the seeded key
make docker-down     # stop it when you're done
```

(`make e2e-docker` runs the same stack as a one-shot end-to-end **test** — ~34
assertions across both planes, then it tears everything down. See
[doc/full_run.md](doc/full_run.md).)

Or bare-metal, for a hot-reload dev loop:

```bash
uv run python scripts/stub_provider.py &   # fake upstream provider on :9099
make api &                                 # governance-api on :8080
make ui &                                  # Vue UI on :5173
make proxy                                 # installs litellm[proxy] extra, runs LiteLLM on :4000
```

`make proxy` installs the `litellm[proxy]` extra and starts the proxy on :4000,
wired to our custom-auth hook. Once installed, `make dev` will auto-detect it
and start the proxy too. Full walkthrough (both options), including a sample
authenticated `/v1/chat/completions` call and troubleshooting:
[doc/full_run.md](doc/full_run.md).

Test / lint:

```bash
make test            # unit: pytest (+ coverage) and vitest
make e2e             # end-to-end: boots the real server, drives the API over HTTP
make e2e-docker      # full-system QA: docker compose up + ~34 assertions across both planes, then teardown
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
- **AWS (CDK):** one-stack deploy of both planes + admin UI to ECS Fargate behind
  an ALB, with RDS PostgreSQL as the source of truth and Bedrock providers via IAM
  (no API keys). See below and the [AWS deployment guide](doc/aws-cdk-deployment.md).
- Operations, upgrades, secrets, scaling, and incident response: [`doc/runbook.md`](doc/runbook.md).

### AWS (CDK) quickstart

The CDK app lives in [`ai-gateway-stack/`](ai-gateway-stack/) (TypeScript). Phase 1
deploys a single stack that serves a governed request end to end: an Application
Load Balancer path-routed to three ECS Fargate services (admin UI on `/`, control
plane on `/api/*` `/docs`, data plane on `/v1/*`), backed by RDS PostgreSQL shared
by both planes, with DB credentials in Secrets Manager. There is no shared
filesystem — the data plane runs `scripts/compile_config.py` at boot to generate
its LiteLLM config from the DB.

```
Internet ─▶ ALB :80
              ├── /            ─▶ Admin UI      (Fargate)
              ├── /api/* /docs ─▶ Control plane (Fargate) ─┐
              └── /v1/*        ─▶ Data plane    (Fargate) ─┤ self-compiles config
                                                           │
                              RDS PostgreSQL ◀──both planes, source of truth
```

**Prerequisites:** Node 20+, Docker running (images build locally as CDK assets),
AWS credentials. Bootstrap once per account/region: `npx cdk bootstrap`.

```bash
cd ai-gateway-stack
npm install
npm run build                          # tsc
npx cdk synth                          # render CloudFormation (no AWS calls)
npx cdk deploy -c appName=ai-gateway -c version=v1   # build + push images, create the stack
```

Outputs include `AdminUiUrl`, `ControlPlaneUrl`, and `GatewayUrl`. To serve a real
request with no API keys: enable model access in the **Amazon Bedrock** console,
register a `bedrock` model in the admin UI, then roll the data plane so it
recompiles its config (`aws ecs update-service --cluster <ClusterName> --service
ai-gateway-v1-data-plane --force-new-deployment`), and call
`POST {GatewayUrl}/chat/completions` with a virtual key. Tear down with
`npx cdk destroy -c version=v1`.

Full architecture, rationale, the phased rollout (HA, scale, multi-tenancy, CI/CD),
security, and cost: [`doc/aws-cdk-deployment.md`](doc/aws-cdk-deployment.md);
stack-specific commands: [`ai-gateway-stack/README.md`](ai-gateway-stack/README.md).

[uv]: https://docs.astral.sh/uv/
