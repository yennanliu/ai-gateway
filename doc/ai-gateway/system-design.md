# AI Gateway — System Design

> **Status:** Draft v3
> **Author:** Platform team
> **Related:** [`litellm-evaluation.md`](./litellm-evaluation.md) · [`implementation-plan.md`](./implementation-plan.md) · [`deployment-and-gtm.md`](./deployment-and-gtm.md)
>
> **Stack decisions:** Backend **Python + FastAPI**, managed with **uv**; **SQLite** as the default datastore (Postgres optional at scale); frontend **Vue 3**; **test-driven development (TDD)** throughout; a **simple single-command local dev** path is a first-class requirement.

This document specifies the architecture for **AI Gateway**, a self-hostable enterprise LLM gateway built on top of **[LiteLLM Proxy](https://docs.litellm.ai/docs/simple_proxy)**. It follows the decision from the evaluation memo: *embed LiteLLM as the routing/adapter core (data plane) and build the product value one layer up (control plane) — org/team governance, billing, compliance/audit, and Agent Builder integration.*

---

## 1. Goals & Non-Goals

### 1.1 Product goals

- **One API, many providers** — a single OpenAI-compatible endpoint in front of OpenAI, Anthropic, Gemini, Bedrock, Azure, and self-hosted models (vLLM/Ollama).
- **BYOK & virtual keys** — customers bring their own provider keys; consumers get scoped virtual keys, never the real ones.
- **Unified usage & cost accounting** — every request is metered, priced, and attributable to an org/team/user/app.
- **Reliability** — automatic fallback and retry when a primary model/provider fails or degrades.
- **Governance** — org → team → user hierarchy, RBAC, budgets, quotas, rate limits.
- **Compliance-ready** — audit trail, data-residency controls, and on-prem/private-cloud deployment to support the ISO 27001 / 27701 story.
- **Extensible** — pluggable guardrails, logging sinks, and billing hooks; tight integration with Agent Builder / Agent 自動化系統.

### 1.2 Non-functional requirements

| Attribute | Target |
|---|---|
| Added latency (gateway overhead, excl. provider) | p50 < 15 ms, p99 < 60 ms |
| Availability | 99.9% (data plane), 99.5% (control plane) |
| Throughput | Horizontally scalable; 5k+ concurrent streams per proxy fleet |
| Streaming | First-token passthrough, no buffering of full response |
| Deployment | Single-command local dev; Docker Compose (small/on-prem); Kubernetes/Helm (scale) |
| Data residency | All request/response data can stay within a customer VPC/on-prem |
| Local dev | Runs on a laptop with **no external services** — SQLite file, in-process cache, stubbed providers |

### 1.3 Non-goals (v1)

- Training / fine-tuning orchestration (only inference + managed fine-tune passthrough where a provider supports it).
- Building our own inference runtime — we route to model servers, we don't serve weights.
- A general-purpose API management product — scope is LLM/agent traffic.

---

## 2. Architecture Overview

The system splits into a **data plane** (the request hot path, must be fast and highly available) and a **control plane** (management, governance, billing — can tolerate brief downtime without stopping inference).

```mermaid
flowchart TB
    subgraph Clients
        SDK[OpenAI-compatible SDKs]
        AB[Agent Builder / Agents]
        APP[Customer apps]
    end

    subgraph Edge
        LB[Ingress / TLS / WAF<br/>coarse rate limit]
    end

    subgraph DataPlane[Data Plane - hot path]
        PROXY[LiteLLM Proxy fleet<br/>stateless, autoscaled]
        HOOKS[Our hooks<br/>auth · guardrails · metering · audit]
        REDIS[(Cache<br/>Redis prod / in-process local)]
    end

    subgraph ControlPlane[Control Plane - management]
        ADMINAPI[Governance API<br/>orgs/teams/keys/policies]
        BILLING[Billing & Usage service]
        UI[Vue Admin UI / self-serve portal]
    end

    subgraph Providers
        OAI[OpenAI]
        ANT[Anthropic]
        BR[Bedrock / Azure / Gemini]
        SELF[Self-hosted vLLM / Ollama]
    end

    subgraph Shared[Shared stores]
        PG[(SQLite default / Postgres at scale<br/>keys, spend, orgs, audit)]
        SECRETS[[Secrets provider<br/>.env dev · Vault/KMS prod]]
        OBS[Observability<br/>OTel · Prometheus · Langfuse]
    end

    SDK & AB & APP --> LB --> PROXY
    PROXY <--> HOOKS
    PROXY <--> REDIS
    PROXY --> OAI & ANT & BR & SELF
    HOOKS --> PG
    HOOKS -. reads provider keys .-> SECRETS
    HOOKS --> OBS

    UI --> ADMINAPI
    ADMINAPI --> PG
    ADMINAPI -. writes provider keys .-> SECRETS
    ADMINAPI -. compiles config / hot-reload .-> PROXY
    BILLING --> PG
    BILLING --> OBS
```

### 2.1 Why this split

- **LiteLLM is the data plane, not the product.** We run it as stateless proxy replicas and extend it via its callback/hook system rather than forking it. Provider adapters, routing, and retries come for free and stay current with vendor API changes. See §4 for the exact integration seams.
- **The control plane is our own service.** Governance, billing, RBAC/SSO, and the branded admin UI live in code we own, backed by our own schema. This is where product differentiation lives and where we avoid the "LiteLLM + a UI skin" trap called out in the evaluation.
- **The two planes share one datastore (SQLite by default, Postgres at scale) + an optional cache + a secrets provider** but have separate failure domains: if the control plane is down, in-flight inference keeps working from cached config.
- **Datastore is pluggable via SQLAlchemy.** SQLite (a single file) is the default — zero-ops for local dev and small on-prem installs; switch to Postgres for HA/scale by changing one connection string. We deliberately keep our own store as the source of truth for keys/spend (via LiteLLM custom-auth hooks) rather than depending on LiteLLM's Prisma/Postgres key store, so SQLite stays viable end-to-end.
- **The cache (Redis) is optional.** Locally it falls back to an in-process implementation so nothing external is required; in production Redis provides shared rate-limit counters and caching across proxy replicas.

---

## 3. Components

### 3.1 Edge / Ingress
- TLS termination, WAF, IP allow/deny, coarse global rate limiting, request-size limits.
- Options: Envoy / Traefik / nginx, or a cloud L7 LB. Kept dumb — no business logic.

### 3.2 LiteLLM Proxy fleet (data plane core)
- Stateless replicas behind the ingress; scale on CPU + concurrent-request metrics.
- Responsibilities it owns: OpenAI-compatible surface, provider adapters, router (fallback/retry/load-balance), streaming.
- Responsibilities we delegate to **our hooks/DB** (not LiteLLM's built-ins): virtual-key auth, budget/quota enforcement, spend accounting, guardrails, audit — see §4.
- Configuration is **generated** from the control-plane DB (see §9), not hand-edited YAML in production.

### 3.3 Our hooks (our code, loaded into the proxy process)
Implemented as LiteLLM custom-auth + custom callbacks / `CustomLogger` and pre/post-call guardrail hooks:
- **Auth:** validate the incoming virtual key against our DB/cache (custom-auth), resolve org/team/app scope.
- **Pre-call:** input guardrails (PII, prompt-injection, secret detection), budget/quota + rate-limit enforcement, request enrichment (org/team tags).
- **Post-call:** output guardrails (moderation, schema/JSON validation), token accounting + spend write, audit-log emission, trace/span export.
- Guardrail providers are pluggable (regex/heuristics, Presidio, LLM-judge, or a commercial moderation API).

### 3.4 Governance API (control plane)
- CRUD for orgs, teams, users, apps, roles, policies, and the **model registry**.
- Orchestrates **virtual-key lifecycle** (issue, scope, rotate, expire, revoke) in **our own store**; keys are enforced at the proxy via the custom-auth hook.
- Stores **provider credentials** in the secrets provider (never in the app DB).
- Compiles the LiteLLM config from the registry and triggers hot-reload (see §9).
- Auth: OIDC/SAML SSO for admins; RBAC on every endpoint.

### 3.5 Billing & Usage service
- Consumes usage records, aggregates per org/team/user/model/app, applies rate cards, produces invoices/exports (CSV, webhook to finance/ERP).
- Serves dashboard queries and budget-alert evaluation. (May run in-process with the Governance API for small deployments; separable at scale.)

### 3.6 Admin UI / self-serve portal
- Branded web app (**Vue 3 + Vite + TypeScript + Pinia**). Admin console (governance, model config, billing, audit) + self-serve developer portal (create keys, view usage, playground). Talks only to the Governance/Billing API via a typed client generated from the OpenAPI schema.

### 3.7 Shared stores
- **Relational DB (SQLAlchemy)** — our full schema (orgs, teams, users, keys, spend, policies, audit, rating). **SQLite** file by default; **Postgres** at scale. Same models/migrations for both.
- **Cache (optional)** — **Redis** in production for shared cache, rate-limit counters, router health/state, key cache; **in-process fallback** for local dev so no external service is needed.
- **Secrets provider (pluggable)** — `.env`/file-based dev provider locally; **Vault** or cloud **KMS/Secrets Manager** in production for provider keys and signing material.
- **Observability** — OTel collector → Prometheus/Grafana (metrics), Loki/ELK (logs), Langfuse (LLM traces). Optional locally.

---

## 4. LiteLLM Integration (the data plane)

**Yes — LiteLLM Proxy *is* our data plane.** We do not fork it and we do not build our own provider adapters/router. We consume LiteLLM as a **pinned dependency** and extend it only through its documented extension points. Everything that is "our product" lives in the control plane and in the hooks we inject.

### 4.1 What we use vs. own vs. ignore

| Concern | Source | Notes |
|---|---|---|
| OpenAI-compatible API surface | **LiteLLM** | `/v1/*` endpoints, streaming |
| Provider adapters (OpenAI, Anthropic, Bedrock, …) | **LiteLLM** | Kept current upstream |
| Router: fallback, retry, load-balance | **LiteLLM** | Configured by our compiler |
| Virtual-key authentication | **Ours** (custom-auth hook) | Validates against our DB/cache — no LiteLLM key store |
| Budgets / quotas / rate limits | **Ours** (pre-call hook) | Enforced against our counters |
| Spend/usage accounting | **Ours** (post-call hook → `UsageRecord`) | Our schema is source of truth |
| Guardrails (PII, injection, moderation) | **Ours** (pre/post hooks) | Pluggable providers |
| Audit logging | **Ours** (hook → `AuditEvent`) | Compliance evidence |
| Model/routing configuration | **Ours** (config compiler → LiteLLM config) | Registry-driven, not hand-edited |
| Admin UI, governance, billing, SSO | **Ours** (control plane) | The product |
| LiteLLM's own admin UI / Prisma / Postgres key store | **Ignored** | We replace these to stay SQLite-friendly and own the UX |

### 4.2 Integration seams (the contract with LiteLLM)

```mermaid
flowchart LR
    subgraph LiteLLM Proxy process
        CORE[LiteLLM core<br/>router + adapters]
        AUTH{{custom-auth hook}}
        CB{{custom callbacks / CustomLogger}}
        CFG[[config file:<br/>model_list · router_settings · general_settings]]
    end
    OURS[[our hooks package<br/>installed via uv]] --> AUTH & CB
    COMPILER[control-plane config compiler] --> CFG
    AUTH --> DB[(our DB / cache)]
    CB --> DB
    CB --> OBS[OTel / Langfuse]
```

We depend on exactly four surfaces, each wrapped behind our own adapter module so an upstream change is localized (see §11):

1. **Custom-auth callable** — signature that receives the request + API key and returns an auth object (or raises). We resolve the virtual key here.
2. **Callback / `CustomLogger` interface** — `pre`/`post`/`success`/`failure` hooks for guardrails, metering, audit, tracing.
3. **Config schema** — `model_list`, `router_settings`, `general_settings` (what our compiler emits).
4. **OpenAI-compatible request/response shape** — the wire contract clients rely on.

### 4.3 How the hooks are delivered
Our hooks ship as a normal Python package (`data-plane/hooks`) added to the LiteLLM image/venv via `uv`, and referenced from the generated config (`general_settings.callbacks` / custom-auth path). No source changes to LiteLLM. The proxy and the control plane are **separate processes** that share the DB/cache; the proxy imports our hook package in-process for the hot path.

---

## 5. Core Features

### 5.1 Unified inference API
OpenAI-compatible: `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/rerank`, `/v1/images`, `/v1/audio/*`, plus `/v1/models`. Streaming (SSE) supported end-to-end. Provider-native passthrough routes for features not covered by the OpenAI schema.

### 5.2 Multi-provider routing & fallback
Router strategies exposed as policy: `priority` (primary → fallback chain), `weighted` (A/B, canary), `latency-based`, `cost-based`, and `tag-based` (route by capability, e.g. `vision`, `long-context`, `on-prem-only`). Health checks + circuit breaking evict unhealthy deployments; automatic retry with exponential backoff on transient errors.

### 5.3 Virtual keys & BYOK
- Provider keys are entered once, encrypted in the secrets provider.
- Consumers receive **virtual keys** scoped to: allowed models, budget, TPM/RPM limits, expiry, and metadata tags. Rotation and revocation are instant (cache invalidation).

### 5.4 Governance & RBAC
Hierarchy: **Org → Team → User/App**. Roles: `org-admin`, `team-admin`, `developer`, `billing-viewer`, `auditor`. Every governance action is authorized and audit-logged.

### 5.5 Budgets, quotas & rate limits
Multi-level and cumulative: per key / user / team / org, and per model. Budgets in currency; quotas in tokens; rate limits in RPM/TPM. Soft (alert) and hard (block) thresholds; period resets (daily/monthly).

### 5.6 Cost & usage tracking + billing
Per-request token + cost capture, priced via a configurable rate card (supports markup over provider cost). Aggregations feed dashboards, budget alerts, invoices, and exports.

### 5.7 Guardrails
Input and output guardrails: PII detection/redaction, prompt-injection detection, secret scanning, content moderation, and JSON-schema/output validation. Configurable per org/team/route; fail-open or fail-closed per policy.

### 5.8 Caching
Exact-match and optional semantic caching (embedding similarity) to cut cost/latency; per-route TTL and opt-out.

### 5.9 Observability & audit
Metrics (latency, tokens, error rates, cost) to Prometheus; LLM request/response traces to Langfuse (with configurable PII redaction/sampling); immutable audit log of admin + inference events for compliance.

### 5.10 Model registry & config management
UI/DB-driven registry of model deployments (provider, credentials ref, limits, routing tags). The control plane compiles this into LiteLLM config and hot-reloads the proxy — no manual YAML edits in prod.

### 5.11 Agent Builder integration
First-class tool/function-calling and streaming passthrough, MCP server compatibility, and per-agent virtual keys with their own budgets and guardrail profiles.

---

## 6. API Reference

Two distinct API surfaces. **OpenAPI is the source of truth** for the control-plane API and generates the Vue client; the list below is representative, not exhaustive. All control-plane paths are versioned under `/api/v1`; responses are JSON with a consistent error envelope (`{error: {code, message, details}}`) and cursor pagination (`?cursor=&limit=`).

### 6.1 Data-plane (inference) API — served by LiteLLM proxy
Auth: `Authorization: Bearer <virtual-key>`. OpenAI-compatible, so existing SDKs work unchanged.

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/chat/completions` | Chat completions (streaming + non-streaming) |
| POST | `/v1/completions` | Legacy text completions |
| POST | `/v1/embeddings` | Embeddings |
| POST | `/v1/rerank` | Reranking |
| POST | `/v1/images/generations` | Image generation |
| POST | `/v1/audio/transcriptions` · `/v1/audio/speech` | STT / TTS |
| GET | `/v1/models` | Models visible to the calling key |
| POST | `/v1/moderations` | Content moderation |
| \* | `/v1/<provider>/*` | Provider-native passthrough for non-OpenAI features |

### 6.2 Control-plane (management) API — served by our Governance/Billing service
Auth: admin session (OIDC) or admin API token; **RBAC enforced per route** (role noted).

**Auth & session**
| Method | Path | Purpose | Role |
|---|---|---|---|
| GET | `/api/v1/auth/login` · `/auth/callback` | OIDC/SAML login flow | — |
| GET | `/api/v1/me` | Current user + roles | any |

**Orgs / Teams / Users / Apps**
| Method | Path | Purpose | Role |
|---|---|---|---|
| GET/POST | `/api/v1/orgs` | List / create orgs | org-admin |
| GET/PATCH/DELETE | `/api/v1/orgs/{id}` | Read / update / delete org | org-admin |
| GET/POST | `/api/v1/teams` | List / create teams | org/team-admin |
| GET/PATCH/DELETE | `/api/v1/teams/{id}` | Manage a team | team-admin |
| GET/POST | `/api/v1/users` · `/memberships` | Manage users & role assignments | org/team-admin |
| GET/POST | `/api/v1/apps` | Manage apps (agent/service consumers) | team-admin |

**Virtual keys**
| Method | Path | Purpose | Role |
|---|---|---|---|
| POST | `/api/v1/keys` | Issue key (plaintext returned once) | team-admin/developer |
| GET | `/api/v1/keys` · `/keys/{id}` | List / inspect (never returns secret) | developer |
| POST | `/api/v1/keys/{id}/rotate` | Rotate | team-admin |
| POST | `/api/v1/keys/{id}/revoke` | Revoke immediately | team-admin |

**Provider credentials & model registry**
| Method | Path | Purpose | Role |
|---|---|---|---|
| GET/POST | `/api/v1/provider-credentials` | Register provider keys (→ secrets store) | org-admin |
| GET/POST | `/api/v1/models` | List / add model deployments | org-admin |
| PATCH/DELETE | `/api/v1/models/{id}` | Update / remove deployment | org-admin |
| POST | `/api/v1/models/{id}/test` | Smoke-test a deployment | org-admin |

**Policies / budgets / rate cards**
| Method | Path | Purpose | Role |
|---|---|---|---|
| GET/PUT | `/api/v1/policies?scope=` | Guardrail/routing/caching policy at a scope | org/team-admin |
| GET/PUT | `/api/v1/budgets?scope=` | Budgets & thresholds at a scope | org/team-admin, billing |
| GET/PUT | `/api/v1/rate-cards` | Pricing + markup | org-admin, billing |

**Usage, billing & audit (reporting)**
| Method | Path | Purpose | Role |
|---|---|---|---|
| GET | `/api/v1/usage?group_by=&from=&to=` | Aggregated usage/cost | billing-viewer+ |
| GET | `/api/v1/invoices` · `/invoices/{id}` | Invoices / period rollups | billing-viewer+ |
| GET | `/api/v1/exports/usage.csv` | CSV export | billing-viewer+ |
| GET | `/api/v1/audit?actor=&action=&from=&to=` | Query audit log | auditor |

**Admin / system**
| Method | Path | Purpose | Role |
|---|---|---|---|
| GET | `/healthz` · `/readyz` | Liveness / readiness (each service) | — |
| GET | `/api/v1/version` | AI Gateway version + tested LiteLLM version (see §11) | any |
| POST | `/api/v1/config/compile` | Recompile LiteLLM config from registry | org-admin |
| POST | `/api/v1/config/reload` | Trigger proxy hot-reload | org-admin |

---

## 7. Request Lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant E as Edge (TLS/WAF)
    participant P as LiteLLM Proxy
    participant H as Our hooks (auth/guardrails/metering)
    participant R as Cache
    participant M as Provider / Model
    participant D as Datastore (SQLite/PG)

    C->>E: POST /v1/chat/completions (virtual key)
    E->>P: forward (coarse rate limit ok)
    P->>H: custom-auth: validate key, load scope + budget
    H->>R: read cached key/budget (miss -> D)
    P->>H: pre-call: input guardrails + budget/quota + rate limit
    alt blocked (guardrail / budget / rate)
        H-->>C: 4xx (policy violation / quota exceeded / 429)
    else allowed
        P->>M: routed call (primary; retry/fallback on failure)
        M-->>P: response / token stream
        P->>H: post-call: output guardrails + token accounting
        H->>D: write usage record + audit event
        H->>R: increment rate/budget counters
        P-->>C: response (streamed)
    end
```

Key properties: streaming is not buffered (guardrails on streams run on chunks or on a post-hoc sample per policy); spend logging is async/non-blocking on the hot path where possible; a control-plane outage does not stop inference because key/budget scope is cached (Redis in prod, in-process locally). Virtual-key validation is done via LiteLLM's **custom-auth hook** against our own store, so no LiteLLM Prisma/Postgres key store is required.

---

## 8. Data Model

This is **our** schema and the single source of truth for keys and spend — we do not use LiteLLM's own key/spend tables (LiteLLM authenticates via a custom-auth hook that calls back into this store, see §4). Defined once with SQLAlchemy models + Alembic migrations; runs on SQLite (default) or Postgres unchanged. `jsonb` columns map to native `JSONB` on Postgres and `JSON`/`TEXT` on SQLite; array columns map to a JSON column on SQLite.

### 8.1 Entity relationships

```mermaid
erDiagram
    ORG ||--o{ TEAM : has
    ORG ||--o{ USER : has
    ORG ||--o{ PROVIDER_CREDENTIAL : owns
    ORG ||--o{ MODEL_DEPLOYMENT : owns
    ORG ||--o{ RATE_CARD : defines
    TEAM ||--o{ APP : has
    TEAM ||--o{ VIRTUAL_KEY : issues
    APP  ||--o{ VIRTUAL_KEY : "may scope"
    USER ||--o{ MEMBERSHIP : has
    TEAM ||--o{ MEMBERSHIP : has
    PROVIDER_CREDENTIAL ||--o{ MODEL_DEPLOYMENT : backs
    VIRTUAL_KEY ||--o{ USAGE_RECORD : generates
    MODEL_DEPLOYMENT ||--o{ USAGE_RECORD : serves
```

### 8.2 Core entities

```
Org(id, name, plan, data_region, created_at)
Team(id, org_id, name, default_budget, created_at)
User(id, org_id, email, sso_subject, status)
Membership(user_id, team_id, role)                 -- RBAC edge
App(id, team_id, name, description)                -- an agent / service consumer

VirtualKey(id, hashed_key, prefix, team_id, app_id, allowed_models[],
           budget, tpm_limit, rpm_limit, expires_at, status, created_at)

ProviderCredential(id, org_id, provider, secret_ref, status)  -- secret_ref -> Vault/KMS
ModelDeployment(id, org_id, public_name, provider, model, credential_id,
                routing_tags[], tpm_limit, rpm_limit, cost_overrides, status)

Policy(id, scope_type, scope_id, guardrails jsonb, routing jsonb, caching jsonb)
Budget(id, scope_type, scope_id, period, limit, soft_pct, hard_pct, spent, resets_at)

UsageRecord(id, ts, key_id, team_id, org_id, model, prompt_tokens,
            completion_tokens, cost, cached, latency_ms, status, request_id)
AuditEvent(id, ts, actor, action, target, before jsonb, after jsonb, ip)
RateCard(id, org_id, model, unit, price, markup_pct)
```

### 8.3 Notes
- `scope_type ∈ {org, team, user, app, key}` lets budgets/policies attach at any level and resolve **most-specific-wins** (key > app > user > team > org).
- `VirtualKey.hashed_key` stores a hash only; `prefix` (e.g. `sk-ag-ab12…`) is shown in the UI for identification. The plaintext key is returned exactly once at creation.
- `UsageRecord` denormalizes `org_id`/`team_id` for fast aggregation; indexed on `(org_id, ts)` and `(team_id, ts)`.
- `AuditEvent` is append-only; no update/delete path in the API.

---

## 9. Configuration Flow (registry → proxy)

The control plane is the source of truth; LiteLLM config is a derived artifact.

```mermaid
flowchart LR
    UI[Vue Admin UI] --> API[Governance API]
    API --> DB[(SQLite / Postgres registry)]
    API --> GEN[Config compiler]
    GEN --> CFG[LiteLLM config file]
    CFG --> RELOAD[Hot reload / rolling restart]
    RELOAD --> PROXY[LiteLLM Proxy fleet]
    API -. cache invalidation .-> REDIS[(Cache: Redis / in-process)]
```

Flow: admin edits a model/policy → Governance API validates + writes to the DB → config compiler renders LiteLLM's model/router config → proxy hot-reloads and caches are invalidated. Virtual keys live in our DB and are validated via LiteLLM's custom-auth hook (no separate key store to sync). This keeps YAML out of human hands in production (a top risk in the evaluation) and makes every config change audited and reversible.

---

## 10. Runtime & Startup (how it runs)

### 10.1 Processes
A full deployment is a handful of processes that share the DB/cache/secrets:

| Process | What it is | Depends on |
|---|---|---|
| `governance-api` (+ billing) | Our FastAPI control plane | DB (migrated), secrets |
| `litellm-proxy` (+ our hooks) | The data plane | Generated config file, DB/cache (for custom-auth), secrets |
| `admin-ui` | Vue app (static build in prod; Vite dev server locally) | governance-api |
| Edge/ingress | TLS/WAF/LB | the services |
| DB · cache · secrets · OTel | Backing services | — |

### 10.2 Do we start LiteLLM first? — No.
**The control plane comes up first because it is the source of truth and it *generates the proxy's config*.** The proxy also needs the DB/cache reachable for key auth. Startup order:

```mermaid
flowchart LR
    A[1. DB up + migrations] --> B[2. Secrets available]
    B --> C[3. governance-api starts]
    C --> D[4. compile initial LiteLLM config from registry]
    D --> E[5. litellm-proxy starts with config + our hooks]
    E --> F[6. admin-ui + edge]
```

1. **Datastore ready & migrated** (`alembic upgrade head`).
2. **Secrets provider reachable** (`.env` locally, Vault/KMS in prod).
3. **`governance-api` starts** — becomes ready once DB + secrets are reachable.
4. **Config compile** — the control plane renders the current LiteLLM config from the registry. **First-boot bootstrap:** if the registry is empty, it emits a minimal valid config (zero models) so the proxy can still start healthy; admins then add models via the UI → recompile → hot-reload. This resolves the chicken-and-egg.
5. **`litellm-proxy` starts** with the generated config and our hooks package installed; its readiness is gated on *config present* + *DB/cache reachable* (so custom-auth works).
6. **`admin-ui` and edge** come up last.

After boot the two planes are **loosely coupled**: if `governance-api` restarts, the proxy keeps serving using cached key/budget state and its last config — only *new* config changes pause until the control plane returns.

### 10.3 Running it locally
`make dev` performs this whole sequence for you and then runs the three app processes concurrently with hot reload:

```bash
uv sync                      # deps
uv run alembic upgrade head  # 1. migrate SQLite
uv run scripts/seed.py       # demo org/team/key/model (also compiles config)
make dev                     # starts governance-api, litellm-proxy(+hooks), vue — concurrently
```

You do **not** start LiteLLM by hand — `make dev` compiles the config from the seeded registry and launches the proxy for you. With the stub provider enabled, no real provider key is required.

---

## 11. Dependency & Version Management (LiteLLM upgrades)

LiteLLM is upstream infrastructure we track deliberately — the evaluation flagged "upstream drift / breaking changes" as a top risk.

### 11.1 Pinning
- LiteLLM is pinned to an **exact version** in `uv.lock`; the proxy Docker image is pinned by **digest**. Nothing floats.
- We **never fork**. If we need an unreleased fix, we pin to a specific upstream git SHA temporarily and track the corresponding PR until it releases.

### 11.2 The contract we depend on
Our coupling is limited to the four seams in §4.2 (custom-auth callable, callback/`CustomLogger` interface, config schema, OpenAI wire shape). Each is wrapped behind an adapter module in `data-plane/hooks`, so an upstream change touches one file, not the whole codebase.

### 11.3 Contract tests (the guard)
A dedicated `tests/contract/litellm/` suite runs against the pinned version and asserts every seam still works:
- our hooks package **loads** in the proxy;
- **custom-auth** accepts a valid virtual key and rejects an unknown/expired one;
- a `chat/completions` and an `embeddings` call succeed through the **stub provider**;
- the **config compiler output loads** without error and routing/fallback behaves.

These run in CI on every LiteLLM bump and nightly.

### 11.4 Upgrade workflow
```mermaid
flowchart LR
    A[Renovate/Dependabot opens bump PR] --> B[CI: contract + e2e smoke on pinned version]
    B --> C[Review upstream CHANGELOG vs our 4 seams]
    C --> D[Deploy to staging + load test + canary]
    D --> E[Promote: update pin + image digest]
    E --> F[Tag release; record tested LiteLLM version]
```
- **Cadence:** scheduled review (e.g. monthly) plus an **expedited path for security fixes**. We test skip-version upgrades before adopting them.
- **Rollback:** images pinned by digest + blue/green means the previous version is always redeployable; DB migrations stay backward-compatible within a release window.
- **Security:** watch LiteLLM advisories/CVEs and transitive deps; `uv` dependency audit in CI.

### 11.5 Compatibility matrix (surfaced to users)
We maintain a table mapping each **AI Gateway release → tested LiteLLM version(s)**, published in release notes and exposed at `GET /api/v1/version` and the UI "About" page, so operators know exactly which upstream version their install was validated against.

| AI Gateway | Tested LiteLLM | Notes |
|---|---|---|
| 0.1.x | `vX.Y.Z` | initial |
| 0.2.x | `vX.Y.Z` | … |

---

## 12. Deployment Topologies

> Commercial packaging — **SaaS vs. downloadable / self-hosted**, editions, licensing, and pricing — is covered in [`deployment-and-gtm.md`](./deployment-and-gtm.md). This section is the technical topology only.

### 12.0 Local development (keep it simple)
The primary rule: **a developer can clone and run the whole thing with one command and no external services.** See §10.3. Datastore is a local SQLite file, cache falls back to in-process, secrets from `.env`, providers stubbed. `uv run pytest` runs the full suite hermetically for TDD.

### 12.1 Small / on-prem (Docker Compose)
Single node or small cluster: `edge`, `litellm-proxy` (1–2), `governance-api`, `admin-ui`. Datastore can stay **SQLite on a mounted volume** for light installs, or add **Postgres + Redis + Vault** containers when the customer needs HA. Everything runs inside the customer boundary for the private-cloud / data-sovereignty story.

### 12.2 Scale (Kubernetes + Helm)
- LiteLLM proxy as a horizontally-autoscaled `Deployment` (HPA on CPU + concurrency).
- Control-plane services as separate deployments (independent scaling/failure domain).
- Managed **Postgres** (HA) + Redis (cluster/sentinel) — swap from SQLite by changing the connection string; Vault or cloud KMS; OTel collector as DaemonSet.
- Blue/green or rolling for proxy config reloads; PodDisruptionBudgets for availability.

### 12.3 Multi-region / residency
Per-region data-plane stacks so request/response data never leaves the region; control-plane metadata can be regional or global-with-regional-sharding depending on the residency policy on each Org.

---

## 13. Security & Compliance

- **Secrets:** provider keys in the secrets provider (Vault/KMS in prod, `.env` for local dev only); app DB stores references, never plaintext. Envelope encryption; automatic rotation supported.
- **Key hygiene:** virtual keys stored hashed; scoped, expirable, instantly revocable.
- **Isolation:** row-level org scoping on every query; tenant data segregation enforced in the API layer.
- **Transport & at-rest:** TLS everywhere; DB and secret stores encrypted at rest.
- **Audit:** immutable `AuditEvent` for all admin and (optionally) inference events — supports ISO 27001 / 27701 evidence.
- **Data controls:** configurable logging/redaction of prompts/responses; PII guardrails; per-org data-region pinning; retention policies.
- **AuthN/Z:** OIDC/SAML SSO for the console; RBAC on every endpoint; API access only via virtual keys.

> Note the evaluation's caveat: SSO/SAML and some advanced guardrail/audit features sit behind LiteLLM's paid Enterprise tier. We implement SSO, RBAC, audit, and governance in **our** control plane so they are not gated by LiteLLM's license — LiteLLM is used for the OSS data-plane capabilities only.

---

## 14. Observability

- **Metrics:** per-model/team latency, token throughput, error and fallback rates, cache hit rate, cost/min → Prometheus/Grafana with SLO alerts.
- **Traces:** LLM request/response traces to Langfuse (sampling + PII redaction configurable).
- **Logs:** structured JSON logs → Loki/ELK, correlated by request id.
- **Alerts:** budget soft/hard thresholds, provider-outage/fallback spikes, latency SLO breaches → Slack/PagerDuty/webhook.

---

## 15. Project Structure

Monorepo. Python is managed by **uv** with a single workspace lockfile; the Vue app has its own `package.json`. LiteLLM is a pinned dependency we configure and extend — not vendored/forked. Tests live **next to the code** (`tests/` per package) so TDD stays close to the unit under test.

```
ai-gateway/
├── README.md
├── Makefile                            # `make dev`, `make test`, `make seed`, `make lint`
├── pyproject.toml                      # uv workspace root (members: control-plane/*, data-plane)
├── uv.lock                             # single pinned lockfile for all Python (incl. LiteLLM)
├── .env.example                        # local dev config (SQLite path, stub provider, etc.)
│
├── doc/
│   └── ai-gateway/
│       ├── litellm-evaluation.md
│       ├── system-design.md            # this document
│       ├── implementation-plan.md      # TDD build plan
│       └── deployment-and-gtm.md       # SaaS vs self-hosted, editions, pricing
│
├── deploy/
│   ├── docker-compose/                 # on-prem topology (sqlite volume or +postgres/redis)
│   ├── helm/                           # k8s charts (proxy, control plane, deps)
│   └── terraform/                      # cloud infra (VPC, Postgres, Redis, KMS)
│
├── data-plane/
│   ├── litellm/
│   │   ├── config.template.yaml        # rendered from registry, not hand-edited
│   │   └── entrypoint.sh
│   └── hooks/                          # our LiteLLM extension package
│       ├── src/hooks/
│       │   ├── auth.py                  # custom-auth: validate virtual key vs our DB
│       │   ├── adapters.py             # isolates the 4 LiteLLM seams (see §11)
│       │   ├── guardrails/             # PII, injection, moderation, schema
│       │   ├── metering.py             # token accounting + spend write
│       │   ├── audit.py                # audit-event emission
│       │   └── logger.py               # OTel/Langfuse export
│       ├── pyproject.toml
│       └── tests/                      # hook unit tests (stubbed proxy context)
│
├── control-plane/
│   ├── governance-api/                 # orgs/teams/users/keys/policies/registry
│   │   ├── src/governance_api/
│   │   │   ├── api/                     # FastAPI routers (see §6)
│   │   │   ├── domain/                  # entities + policy/budget resolution
│   │   │   ├── services/               # key lifecycle, config compiler
│   │   │   ├── db/                      # SQLAlchemy models + session (SQLite/Postgres)
│   │   │   ├── secrets/                # env(dev) / vault(prod) adapters
│   │   │   └── auth/                    # oidc/saml, rbac
│   │   ├── migrations/                  # alembic (SQLite + Postgres compatible)
│   │   ├── pyproject.toml
│   │   └── tests/                       # unit + api tests (in-memory SQLite)
│   ├── billing/                        # usage aggregation, rating, invoices/exports
│   │   ├── src/billing/
│   │   ├── pyproject.toml
│   │   └── tests/
│   └── config-compiler/                # registry -> litellm config (shared lib)
│       ├── src/config_compiler/
│       └── tests/
│
├── admin-ui/                           # Vue 3 + Vite + TypeScript
│   ├── src/
│   │   ├── views/                       # pages (dashboard, keys, models, usage, audit)
│   │   ├── components/
│   │   ├── stores/                      # Pinia state
│   │   ├── api/                         # typed client (generated from OpenAPI)
│   │   └── router/                      # vue-router
│   ├── tests/                           # vitest + Vue Test Utils
│   ├── package.json
│   └── vite.config.ts
│
├── packages/                           # shared Python libs
│   └── schemas/                        # pydantic models / OpenAPI (source for UI client)
│
├── scripts/                            # dev.sh, seed.py, key-rotate.py, load-test
└── tests/
    ├── contract/litellm/               # LiteLLM version-contract tests (see §11)
    ├── integration/                    # end-to-end request-path (spins api+proxy)
    └── load/                           # k6/locust throughput + latency
```

---

## 16. Technology Choices

| Layer | Choice | Rationale |
|---|---|---|
| Data-plane core | **LiteLLM Proxy** (pinned) | Provider adapters, routing, fallback out of the box |
| Hooks/guardrails | **Python** (LiteLLM callbacks) | Runs in-process with the proxy; same language |
| Control-plane API | **Python + FastAPI** | Async, OpenAPI-native; one language across proxy + control plane |
| Python packaging | **uv** | Fast, reproducible installs; single workspace lockfile for all Python |
| Testing | **pytest** (+ **vitest** for UI); **TDD** | Fast hermetic suite on in-memory SQLite; test-first is the default workflow |
| ORM / migrations | **SQLAlchemy + Alembic** | One data layer that runs unchanged on SQLite and Postgres |
| Datastore | **SQLite (default) → Postgres (scale)** | Zero-ops local/on-prem; swap connection string for HA |
| Admin UI | **Vue 3 + Vite + TypeScript + Pinia** | Requested FE; fast dev server, typed client generated from OpenAPI |
| Cache / state | **Redis (prod) / in-process (local)** | Shared counters+cache at scale; nothing external for local dev |
| Secrets | **`.env` (dev) → Vault/KMS (prod)** | Keep provider keys out of the app DB; simple locally |
| Identity | **OIDC/SAML** (Keycloak or IdP) | Enterprise SSO for the console |
| Observability | **OTel + Prometheus/Grafana + Langfuse** | Metrics + LLM tracing (optional locally) |
| Packaging | **Docker + Helm + Terraform** | Local Compose and scaled k8s from one codebase |

> **Local-first principle:** every production dependency (Postgres, Redis, Vault, OTel) has a zero-config local fallback (SQLite, in-process cache, `.env`, no-op exporter) so the inner dev/test loop needs nothing but `uv` and Node.
>
> If p99 gateway overhead becomes a bottleneck, the hooks/guardrails layer (not the control plane) is the candidate to rewrite in Go — but start in Python to keep the team on one stack.

---

## 17. Delivery Phases

Aligned with the evaluation's ~2–3 month v1 estimate for a small team. See [`implementation-plan.md`](./implementation-plan.md) for the milestone-level TDD breakdown.

| Phase | Scope | Est. |
|---|---|---|
| **P0 — MVP wrap** | Deploy LiteLLM; wire virtual-key issuance + budgets to our org/team model; config compiler; basic admin UI | 2–3 wk |
| **P1 — Product integration** | Usage → billing/dashboard (own UI, not LiteLLM default); rate cards; Agent Builder integration | 3–5 wk |
| **P2 — Differentiation** | Guardrails suite, deeper audit/compliance logging, org/team governance UI, private-model registry | 4–8 wk+ |
| **P3 — Enterprise hardening** | HA deploy, secrets management, rate-limit tuning, security review, on-prem packaging, SSO/SAML | 2–4 wk |

---

## 18. Key Risks & Mitigations

| Risk (from evaluation) | Mitigation in this design |
|---|---|
| "LiteLLM + a UI skin" — weak differentiation | Product value in the control plane: governance, billing, compliance, Agent Builder integration |
| Enterprise features behind LiteLLM's paid tier | Implement SSO, RBAC, audit, governance in our own control plane |
| YAML config unwieldy at scale | Registry-driven config compiler; no hand-edited prod YAML (§9) |
| Upstream drift / breaking changes | Pin LiteLLM version; contract tests + compatibility matrix; staged upgrades (§11) |
| Operational ownership (uptime/patching) | Stateless autoscaled proxy, HA stores, blue/green reloads, SLO alerting |
| OSS-only support risk for SLA product | Own the control plane + runbooks; evaluate LiteLLM enterprise support only where it buys real leverage |

---

## 19. Open Questions

- Do we run guardrails inline on streamed responses (chunk-level, higher latency) or async-sample (lower latency, weaker guarantee)? Likely policy-configurable per route.
- Semantic cache: worth the embedding cost/latency, or start exact-match only?
- Multi-region metadata: global control plane with regional data plane, or fully regional stacks?
- Billing: build rating/invoicing in-house or integrate an existing metering/billing system?
- How deep does Agent Builder integration go in v1 — passthrough tool-calling only, or first-class agent/session objects in our schema?
- Delivery model priority — lead with self-hosted/downloadable or managed SaaS first? (see [`deployment-and-gtm.md`](./deployment-and-gtm.md))
