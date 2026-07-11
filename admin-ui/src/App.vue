<script setup lang="ts">
import { reactive } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const form = reactive({ userId: "admin", orgId: "", roles: "org-admin" });

function login(): void {
  auth.login({ userId: form.userId, orgId: form.orgId, roles: form.roles.split(",") });
}
</script>

<template>
  <header class="topbar">
    <div class="container bar">
      <span class="wordmark">AI&nbsp;GATEWAY</span>
      <nav v-if="auth.isAuthenticated">
        <RouterLink to="/">Dashboard</RouterLink>
        <RouterLink to="/models">Models</RouterLink>
        <RouterLink to="/keys">Keys</RouterLink>
        <RouterLink to="/usage">Usage</RouterLink>
        <RouterLink to="/budgets">Budgets</RouterLink>
      </nav>
      <span class="spacer" />
      <span v-if="auth.isAuthenticated" class="who">
        {{ auth.principal?.userId }} · {{ auth.principal?.orgId?.slice(0, 8) }}
        <button class="btn btn-secondary" @click="auth.logout">Sign out</button>
      </span>
    </div>
  </header>

  <main>
    <section v-if="!auth.isAuthenticated" class="film">
      <div class="container film-inner">
        <p class="eyebrow">Enterprise LLM gateway</p>
        <h1 class="hero">One API. Every model.<br />Governed, metered, yours.</h1>
        <div class="card signin">
          <p class="muted">Dev sign-in (stand-in until OIDC)</p>
          <div class="row">
            <input v-model="form.userId" placeholder="user id" />
            <input v-model="form.orgId" placeholder="org id" />
            <input v-model="form.roles" placeholder="roles (comma)" />
            <button class="btn btn-primary" :disabled="!form.orgId" @click="login">
              Sign in
            </button>
          </div>
        </div>
      </div>
    </section>

    <div v-else class="container page">
      <RouterView />
    </div>
  </main>
</template>

<style scoped>
.topbar {
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 10;
}
.bar {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  height: 60px;
}
.wordmark {
  font-weight: 500;
  letter-spacing: 0.18em;
  font-size: 14px;
  color: var(--ink);
}
nav {
  display: flex;
  gap: 0.25rem;
}
nav a {
  color: var(--text-muted);
  padding: 0.35rem 0.8rem;
  border-radius: 999px;
  font-size: 14px;
}
nav a:hover {
  color: var(--ink);
}
nav a.router-link-active {
  color: var(--ink);
  background: var(--bg-alt);
}
.spacer {
  flex: 1;
}
.who {
  font-size: 13px;
  color: var(--text-muted);
  display: flex;
  gap: 0.6rem;
  align-items: center;
}
.page {
  padding: 40px 24px 80px;
}

/* Film hero — daylight cinematic gradient (no external assets) */
.film {
  background:
    radial-gradient(120% 90% at 70% -10%, color-mix(in srgb, var(--accent) 22%, transparent), transparent 60%),
    linear-gradient(180deg, var(--bg-alt), var(--bg));
  min-height: calc(100vh - 60px);
  display: flex;
  align-items: center;
}
.film-inner {
  padding: 64px 24px;
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
  margin: 0 0 2.5rem;
}
.signin {
  max-width: 640px;
}
.signin .row {
  margin-top: 0.75rem;
}
.signin input {
  flex: 1;
  min-width: 140px;
}
</style>
