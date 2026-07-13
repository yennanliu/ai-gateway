# Metering write-back (proxy → control-plane DB)

> **Related:** [`system-design.md`](./system-design.md) (§9 config compilation, metering),
> [`testing-and-debugging.md`](./testing-and-debugging.md)

How a live request through the LiteLLM proxy turns into a `UsageRecord` (and a
budget update) in our control-plane DB — and the two-layer bug where it didn't.

## Symptom

A real chat completion through the data plane succeeded (HTTP `200`) but the
usage numbers never moved: `GET /api/v1/usage` kept reporting only the seeded
demo rows, and `group_by=key` showed a single `null`-keyed group. Dashboards and
the site guide therefore reflected **seeded data only**, never live traffic.

## Root cause (two layers)

We extend the LiteLLM proxy through two of its documented seams: **custom-auth**
(`hooks.auth.user_api_key_auth`, authenticates every request against our DB) and
a **`CustomLogger` callback** (`hooks.callbacks.AIGatewayLogger`, whose
`async_log_success_event` calls `services.metering.record_usage`).

1. **The callback was never registered.** `services/config_compiler.py` emitted
   only `general_settings.custom_auth`, never `litellm_settings.callbacks`. The
   proxy loaded the auth hook but never the logger, so nothing wrote usage.

2. **Even once registered, attribution was wrong.** The logger ran but the rows
   it wrote were unusable:
   - `org_id` / `team_id` were `NULL` — so the rows were invisible to the
     org-scoped `GET /api/v1/usage` query.
   - `key_id` was LiteLLM's **hashed token**, not our internal key id.
   - `model` was the **upstream** deployment (`gpt-4o-mini`), not the public
     registry name (`demo-gpt`) — so no `RateCard` matched and `cost` was `0`.

   The auth adapter only put `api_key` + `team_id` on the `UserAPIKeyAuth`
   object, and the callback read the wrong fields out of the success event.

## The fix (four parts)

1. **Emit the callback** — `services/config_compiler.py`:
   ```python
   CALLBACK_INSTANCE_PATH = "hooks.callbacks.aigw_logger"
   ...
   "litellm_settings": {"callbacks": [CALLBACK_INSTANCE_PATH]},
   ```
2. **Export a logger instance** — `hooks/callbacks.py`:
   ```python
   aigw_logger = AIGatewayLogger()
   ```
3. **Emit a callbacks shim next to the config** — `data-plane/litellm/entrypoint.sh`.
   LiteLLM's `get_instance_fn` resolves `litellm_settings.callbacks` as a **file
   relative to the config directory** (`<config_dir>/hooks/callbacks.py`), exactly
   like `custom_auth`. The entrypoint already wrote a `hooks/auth.py` shim; it now
   also writes a `hooks/callbacks.py` shim that re-imports the real instance via
   the normal import system (stripping the config dir from `sys.path` so the
   installed `aigw-hooks` package wins, not the shim dir).
4. **Propagate + read the right scope:**
   - `hooks/auth.py` sets our scope on the auth object: `org_id`, `team_id`,
     `key_alias` = **our** key id, and a `metadata` fallback copy.
   - `hooks/callbacks.py` reads the flattened logging metadata LiteLLM exposes in
     the success event — `user_api_key_org_id`, `user_api_key_team_id`,
     `user_api_key_alias` (our key id), and `model_group` (the public model name)
     — with a fallback to the stashed `user_api_key_metadata`.

Resulting compiled `litellm.config.yaml`:

```yaml
litellm_settings:
  callbacks:
  - hooks.callbacks.aigw_logger
general_settings:
  custom_auth: hooks.auth.user_api_key_auth
```

### Request → record flow

```
client → proxy /v1/chat/completions
       → custom_auth (hooks.auth)                 authenticate vs our DB;
                                                   stamp org/team/key on the auth obj
       → provider call
       → async_log_success_event (hooks.callbacks.aigw_logger)
             scope_from_logging_metadata(kwargs.litellm_params.metadata)
             record_usage(key_id, team_id, org_id, model=model_group, tokens…)
             → INSERT UsageRecord + budget.spent += cost   (shared SQLite/PG)
control plane → GET /api/v1/usage  reads those rows back
```

The proxy container shares `AIGW_DATABASE_URL` with the control plane
(`sqlite:////data/ai-gateway.db` on the compose volume), so the row the proxy
writes is the row the control plane reads.

## How to verify

```bash
make docker-up
ORG=…                                # seed log: "org: <id>"
KEY=…                                # seed log, or POST /api/v1/keys
H=(-H "X-User-Id: admin" -H "X-Org-Id: $ORG" -H "X-Org-Roles: org-admin")

curl -s "${H[@]}" "localhost:8080/api/v1/usage?group_by=key"     # baseline
curl -s localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"model":"demo-gpt","messages":[{"role":"user","content":"hi"}]}' >/dev/null
curl -s "${H[@]}" "localhost:8080/api/v1/usage?group_by=key"     # key row, requests +1, cost > 0
```

Expected: a row keyed by the virtual key's id appears (or its `requests` count
increments), with `model` = the public name and non-zero `cost` (given a rate
card). Confirm attribution end to end with `group_by=model` and the Usage page.

Unit coverage:
- `test_config_compiler.py` — asserts `litellm_settings.callbacks` is emitted.
- `test_callbacks.py::test_scope_from_logging_metadata_*` — flattened keys +
  metadata fallback.
- `test_callbacks.py::test_success_event_records_usage` — records against the
  public model name, attributed to org + key.

## Caveats / follow-ups

- **Enforcement is separate.** This is post-call *accounting*. Live
  budget/rate-limit/guardrail *enforcement* runs in `async_pre_call_hook`
  (`hooks.enforcement`); a revoked key is already rejected by custom-auth on the
  next request (the source-of-truth invariant). The pre-call hook rides on the
  same callback instance as metering, so wiring `litellm_settings.callbacks`
  activated both. Two attribution bugs that made it silently pass-through were
  fixed alongside: `scope_from` must read our key id from `key_alias` (not the
  plaintext `api_key`) or key-scoped budgets never match, and `rpm_limit` must be
  stamped onto the auth object in `hooks/auth.py` or the rate-limit leg is dead.
  All three controls are asserted end-to-end in `scripts/e2e_docker_qa.sh`
  (402 over-budget, 429 rate-limit, 400 injection-guardrail).
- **Redaction rewrites the request.** A `pii: redact` input guardrail now
  substitutes the outbound `data["messages"]` in `async_pre_call_hook` (via
  `enforce_pre_call_messages`), not just a metadata copy — so the redacted text
  is what reaches the provider.
- **Cost needs a rate card.** With no `RateCard` for the org+model the row is
  still written, with `cost = 0`; metering now logs a `WARNING` so that silent
  zero-cost billing is visible.
- **Streaming.** The pre-call hook forces `stream_options.include_usage=true` on
  streamed requests so providers return usage on the final chunk; without it a
  streamed call would meter zero tokens. Asserted by a token-delta check in
  `scripts/e2e_docker_qa.sh`.
- When bumping LiteLLM, re-check the `user_api_key_*` / `model_group` metadata
  keys and `get_instance_fn`'s file-relative resolution alongside the other
  seams (see `COMPATIBLE_LITELLM` in `config.py`).
```
