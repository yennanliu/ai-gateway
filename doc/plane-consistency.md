# Control plane ⇄ data plane consistency

A live verification that the two planes share **one source of truth**. The
governance **control plane** (`governance-api`, `:8080`) and the LiteLLM **data
plane** (`litellm-proxy`, `:4000`) run as separate containers but bind to the
same database. Each operation below is performed on one plane and its effect is
observed on the other.

This is the concrete demonstration of the core invariant in
[`system-design.md`](system-design.md) §4.1: **our SQLite/Postgres DB — not
LiteLLM's own key store — is the source of truth for virtual keys and spend.**
The proxy authenticates every request by calling *back* into that DB via the
custom-auth hook (`hooks/auth.py`) and writes usage *back* after every completion
(`hooks/callbacks.py`), so a control-plane change is visible at the proxy on the
next request with no restart and no second key store.

```
  Control plane (:8080)            shared DB              Data plane (:4000)
  governance-api        ── binds ──▶  /data      ◀── binds ── litellm-proxy
  orgs/teams/keys                ai-gateway.db              OpenAI-compatible /v1/*
  registry / budgets      ▲ custom-auth callback           routing + fallback
  policies / RBAC         ▼ metering write-back             enforces OUR keys/limits
  usage / billing         + compiled LiteLLM YAML           applies OUR guardrails
```

## Reproduce

```bash
make docker-up                 # build + seed + start all containers
./scripts/plane_consistency.sh # run the 11-op matrix against the live stack
make docker-down               # tear down (removes the data volume)
```

`scripts/plane_consistency.sh` derives the seeded org/team/key from the seed
container log, then drives the control plane with `curl` and observes the proxy.

## The matrix (verified)

Legend — `200` allowed · `402`/`429` throttled · `400`/`401`/`403` rejected.

| # | Flow | Operation (control plane) | Effect (other plane) | HTTP |
|---|------|---------------------------|----------------------|------|
| 1 | CP → DP | Issue virtual key (exists only in our DB) | Proxy accepts it next request | `200` |
| 2 | CP → DP | Revoke key (`status → revoked`) | Proxy rejects the same key, live | `401` |
| 3 | CP → DP | Scope key to `demo-gpt` (`allowed_models`) | `demo-gpt` passes; `demo-claude` blocked | `200` / `403` |
| 4 | CP → DP | Set past `expires_at` | Proxy rejects as expired | `401` |
| 5 | CP → DP | Key budget `$0.001/day` (`PUT /budgets`) | 1st call ok, 2nd over budget | `200` / `402` |
| 6 | CP → DP | Rate limit `rpm=2` on the key | 3rd call in the minute throttled | `200`×2 / `429` |
| 7 | DP → CP | 3 completions through the proxy | Usage rows + spend appear in our DB & billing API | `+3` |
| 8 | CP ◂ DP | `GET /data-plane/status` | Control plane surfaces the proxy's effective config | read |
| 9 | CP → DP | Policy `input.pii = redact` | Proxy rewrites outbound prompt: email → `[REDACTED:email]` | `200` |
| 10 | CP → DP | Policy `input.injection = block` | Injection prompt rejected before routing | `400` |
| 11 | CP → DP | Register model + `config/compile` + reload | `demo-echo` unroutable → routable | `400` → `200` |

### Where each gate lives

- **Auth / revoke / expiry / model allowlist** — `hooks/auth.py` (`authenticate`),
  enforced on every request. The allowlist check reads the requested model from
  the request body (`user_api_key_auth`); a scoped-away model is `403`.
- **Budget / rate limit / guardrails** — `hooks/enforcement.py` pre-call hook
  (`402` / `429` / `400`), wired via `hooks/callbacks.py::async_pre_call_hook`.
- **Metering write-back** — `hooks/callbacks.py::async_log_success_event` →
  `governance_api.services.metering.record_usage` (writes a `UsageRecord` and
  updates `Budget.spent`).
- **Model registry → data plane** — `services/config_compiler.py` compiles the
  registry (source of truth) into the derived LiteLLM YAML on the shared volume;
  the proxy loads it on (re)start.

## Notes

- **Ops 9 & 10** set a `Policy` row directly in the store — policies do not yet
  have a public control-plane endpoint. Every other op uses the public API.
- **Op 11** requires a proxy reload. Config hot-reload (`POST /config/reload`) is
  currently an intent-recording stub (system-design §10); the script restarts the
  `litellm-proxy` container to load the recompiled config.
