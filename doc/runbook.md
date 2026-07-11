# AI Gateway — Operations Runbook

> **Related:** [`system-design.md`](./system-design.md) (§10 runtime, §11 versioning, §12 topologies)

Operational procedures for running AI Gateway in production.

## 1. Deploy

### Docker Compose (small / on-prem)
```bash
cd deploy/docker-compose
docker compose up --build                 # SQLite volume, zero external deps
docker compose --profile scale up --build # + Postgres + Redis
```
Services: governance-api `:8080`, litellm-proxy `:4000`, admin-ui `:8081`.

### Kubernetes (Helm)
```bash
helm upgrade --install ai-gateway deploy/helm/ai-gateway \
  --set database.url='postgresql+psycopg://USER:PASS@HOST:5432/aigw' \
  --set image.controlPlane=REGISTRY/ai-gateway-control-plane:TAG \
  --set image.dataPlane=REGISTRY/ai-gateway-proxy:TAG
```
The proxy autoscales via HPA (CPU target 70%, 2–10 replicas by default).

## 2. Startup order (why control plane first)
DB migrated → secrets available → governance-api up → **compile config**
(`POST /api/v1/config/compile`) → proxy starts with the config + hooks →
admin-ui/edge. On an empty registry the proxy still starts (zero models).
The control plane is the source of truth and generates the proxy config, so it
comes up first; the proxy keeps serving from cache if the control plane restarts.

## 3. Config changes (models / routing / policies)
1. Admin edits via API/UI (writes to the DB).
2. `POST /api/v1/config/compile` renders `litellm.config.yaml` (audited).
3. `POST /api/v1/config/reload` (or rolling restart) picks it up.
Never hand-edit the proxy YAML in production — it is a derived artifact.

## 4. Upgrading LiteLLM (see system-design §11)
1. Renovate/Dependabot opens a version bump PR.
2. CI runs contract + e2e smoke against the pinned version.
3. Review the upstream CHANGELOG against our four seams (custom-auth, callbacks,
   config schema, OpenAI wire shape).
4. Deploy to staging, run the load test, canary.
5. Promote: update the pin + image digest; tag the release; record the tested
   LiteLLM version (surfaced at `GET /api/v1/version`).
**Rollback:** images are pinned by digest + blue/green, so redeploy the previous
tag. DB migrations stay backward-compatible within a release window.

## 5. Secrets
Provider keys live in Vault/KMS (never the app DB); the compiled config
references them as `os.environ/<ref>`, so no plaintext is written to disk.
Rotate provider keys in the secrets store; rotate virtual keys via
`POST /api/v1/keys/{id}/rotate` (old secret invalid immediately).

## 6. Scaling & availability
- Proxy is stateless — scale horizontally (HPA on CPU + concurrency).
- Move from SQLite to managed **Postgres** (HA) by changing `AIGW_DATABASE_URL`;
  add **Redis** for shared rate-limit counters + cache across replicas.
- Control plane and data plane are separate failure domains: a control-plane
  outage does not stop in-flight inference (key/budget scope is cached).

## 7. Backups & DR
- Postgres: standard PITR / managed backups. SQLite: back up the volume file.
- The registry (models/policies/keys) is the source of truth — back it up; the
  proxy config can always be recompiled from it.

## 8. Monitoring & alerts
Metrics → Prometheus (latency, tokens, error/fallback rate, cache hit, cost/min);
LLM traces → Langfuse; logs → Loki/ELK. Alert on: budget soft/hard thresholds,
provider-outage/fallback spikes, latency SLO breaches (p99 gateway overhead
< 60ms), and 5xx rate.

## 9. Load testing
```bash
AIGW_ORG_ID=<org> uvx locust -f tests/load/locustfile.py --host http://HOST:8080
```
Target NFRs: p50 < 15ms, p99 < 60ms gateway overhead (excl. provider latency);
5k+ concurrent streams per proxy fleet.

## 10. Incident response (common)
| Symptom | First checks |
|---|---|
| 401 on all requests | control plane reachable? key store / custom-auth healthy? |
| 402 / 429 spikes | budget/rate-limit thresholds; expected traffic change? |
| Provider errors | check fallback routing; provider status; circuit breaker state |
| Proxy won't start | config present + valid? DB/cache reachable? hooks importable? |

## 11. Security review checklist (per release)
- [ ] No plaintext secrets in config, logs, or DB.
- [ ] Virtual keys stored hashed; rotation/revocation verified.
- [ ] RBAC enforced on every mutating endpoint; audit events emitted.
- [ ] TLS in front of edge; DB + secret store encrypted at rest.
- [ ] Dependency + LiteLLM CVE scan clean.
- [ ] Tenant isolation (row-level org scoping) verified.
