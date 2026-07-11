<script setup lang="ts">
import { reactive } from "vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const form = reactive({ userId: "admin", orgId: "", roles: "org-admin" });

function login(): void {
  auth.login({ userId: form.userId, orgId: form.orgId, roles: form.roles.split(",") });
}

const features = [
  {
    title: "One API, every model",
    body: "An OpenAI-compatible endpoint in front of OpenAI, Anthropic, Gemini, Bedrock, and self-hosted models — with automatic routing and fallback.",
  },
  {
    title: "Virtual keys & governance",
    body: "Org → team → app hierarchy, RBAC, and scoped virtual keys. Bring your own provider keys; consumers never see them.",
  },
  {
    title: "Budgets & guardrails",
    body: "Per-scope budgets and rate limits, plus PII, prompt-injection, and schema guardrails enforced on every request.",
  },
  {
    title: "Usage & billing",
    body: "Every call metered and priced. Aggregate by model, team, or day; export invoices; alert before budgets blow.",
  },
];
</script>

<template>
  <section class="film">
    <div class="container film-inner">
      <p class="eyebrow">Enterprise LLM gateway</p>
      <h1 class="hero">One API. Every model.<br />Governed, metered, yours.</h1>
      <p class="sub muted">
        Self-hostable control plane on top of LiteLLM — keep your data in your
        boundary, govern access, and see every token and dollar.
      </p>

      <div class="card signin">
        <p class="muted">Dev sign-in (stand-in until OIDC)</p>
        <div class="row">
          <input v-model="form.userId" placeholder="user id" />
          <input v-model="form.orgId" placeholder="org id" />
          <input v-model="form.roles" placeholder="roles (comma)" />
          <button class="btn btn-primary" :disabled="!form.orgId" @click="login">
            Enter console
          </button>
        </div>
        <p class="hint muted">
          Tip: run <code>make seed</code> to get an org id and a ready virtual key.
        </p>
      </div>
    </div>
  </section>

  <section class="container features">
    <div class="feature card" v-for="f in features" :key="f.title">
      <h3>{{ f.title }}</h3>
      <p class="muted">{{ f.body }}</p>
    </div>
  </section>
</template>

<style scoped>
.film {
  background:
    radial-gradient(120% 90% at 72% -10%, color-mix(in srgb, var(--accent) 22%, transparent), transparent 60%),
    linear-gradient(180deg, var(--bg-alt), var(--bg));
  display: flex;
  align-items: center;
  padding: 72px 0 48px;
}
.film-inner {
  padding: 24px;
}
.eyebrow {
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 12px;
  color: var(--accent);
  margin: 0 0 0.75rem;
}
.hero {
  font-size: clamp(36px, 6vw, 64px);
  font-weight: 300;
  line-height: 1.05;
  letter-spacing: -0.02em;
  margin: 0 0 1rem;
}
.sub {
  max-width: 560px;
  font-size: 18px;
  margin: 0 0 2rem;
}
.signin {
  max-width: 680px;
}
.signin .row {
  margin-top: 0.75rem;
}
.signin input {
  flex: 1;
  min-width: 140px;
}
.hint {
  margin: 0.75rem 0 0;
  font-size: 13px;
}
.features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 20px;
  padding-top: 24px;
  padding-bottom: 80px;
}
.feature h3 {
  font-size: 18px;
}
.feature p {
  margin: 0;
  font-size: 14px;
}
</style>
