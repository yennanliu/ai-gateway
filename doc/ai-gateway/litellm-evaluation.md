# Building `AI Gateway` on top of LiteLLM Proxy — Evaluation

Reference: https://docs.litellm.ai/docs/simple_proxy

**Bottom line: yes, build on it rather than from scratch.** LiteLLM Proxy already solves the hard, undifferentiated 80% (provider adapters, routing, auth) — your job becomes packaging + the 20% that's actually your product.

## What LiteLLM Proxy gives you out of the box

- **Unified API**: one OpenAI-compatible endpoint in front of 100+ models/providers (OpenAI, Anthropic, Gemini, Bedrock, Azure, open-source via Ollama/vLLM, etc.) — exactly the "一個 API 串接多家 LLM" pitch from the solutions page.
- **Virtual keys**: issue per-team/per-app API keys without exposing real provider keys — maps directly to the BYOK story.
- **Spend tracking & budgets**: per-key/per-user cost limits and usage tracking — covers the "用量與費用統一記錄" requirement.
- **Routing & reliability**: load balancing, automatic fallback/retry across models/providers, cost-based routing — this is the "主力掛掉自動 fallback" feature, already built.
- **Observability hooks**: logging/alerting integrations (Slack, Datadog, Langfuse, etc.).
- **Caching**: prompt/response caching to cut cost.
- **Deployment**: Docker image + YAML config + admin UI — can be self-hosted (fits the On-Premise/私有雲 story) or run as a sidecar.
- **License**: core proxy is open source (MIT); some enterprise features (SSO, advanced guardrails/audit, dedicated support) are gated behind a paid tier.

## Pros of building on LiteLLM

| Area | Benefit |
|---|---|
| Time-to-market | Skip months of writing provider adapters, retry/fallback logic, and a routing engine |
| Battle-tested | Widely adopted, active OSS community, provider adapters kept up to date as vendors change APIs |
| OpenAI-compatible | Any tool/SDK that already speaks the OpenAI API works against it immediately |
| Self-hostable | Fits the data-sovereignty / on-prem deployment story without extra engineering |
| Extensible | Custom callback/plugin hooks let you bolt on your own guardrails, logging sinks, or billing logic |

## Cons / risks

| Area | Concern |
|---|---|
| Differentiation | If the "AI Gateway" is just LiteLLM + a UI skin, it's hard to justify as a distinct product — needs a real value-add (see below) |
| Enterprise feature wall | Some things enterprises ask for (SSO/SAML, advanced audit logs, some guardrail features) sit behind LiteLLM's paid Enterprise tier — either pay for it, reimplement it, or accept the gap |
| Operational ownership | Still own uptime, scaling, upgrades, security patching of the proxy itself — it's infra you run, not a managed dependency |
| Config complexity | YAML-based model/routing config can get unwieldy at scale; likely want a UI/DB layer on top rather than hand-editing YAML in production |
| Upstream drift | Coupled to LiteLLM's release cadence and breaking changes; provider-specific quirks sometimes lag behind actual provider updates |
| Support model | OSS community support only unless paying for their enterprise support — riskier for an SLA-backed product |

## Effort estimate

Assuming a small team (1–2 backend engineers):

| Phase | Scope | Effort |
|---|---|---|
| MVP wrap | Deploy LiteLLM proxy, wire virtual-key issuance + budgets to own auth/org model, basic admin UI for model config | **2–3 weeks** |
| Product integration | Connect usage/cost data into billing, build own dashboard (don't rely on LiteLLM's default UI for a branded product), add Agent Builder integration | **3–5 weeks** |
| Differentiation layer | Whatever makes it *the* gateway — e.g. custom guardrails tuned for customers, deeper audit/compliance logging for ISO 27001 story, org/team-level governance UI, private-model registry | **4–8+ weeks**, ongoing |
| Hardening for enterprise | HA deployment, secrets management, rate-limit tuning, security review, on-prem packaging | **2–4 weeks** |

**Total to a credible v1: ~2–3 months** for a small team, versus likely 4–6+ months to build equivalent routing/fallback/cost-tracking from scratch.

## Recommendation

Build on LiteLLM Proxy as the routing/adapter core, but treat it as infrastructure to embed, not the product itself. The actual product differentiation should live one layer up: org/team governance, billing integration tied to the platform, compliance/audit features for the ISO 27001/27701 story, and tight integration with Agent Builder and Agent 自動化系統 — things LiteLLM doesn't provide out of the box. That framing also matches how AI Gateway is already positioned on the site ("測試中" / enterprise model entry point) rather than as a bare proxy.
