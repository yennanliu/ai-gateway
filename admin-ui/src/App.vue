<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import LandingView from "@/views/LandingView.vue";

const auth = useAuthStore();
const theme = useThemeStore();
</script>

<template>
  <header class="topbar">
    <div class="container bar">
      <RouterLink to="/" class="wordmark">AI&nbsp;GATEWAY</RouterLink>
      <nav v-if="auth.isAuthenticated">
        <RouterLink to="/">Dashboard</RouterLink>
        <RouterLink to="/models">Models</RouterLink>
        <RouterLink to="/teams">Teams</RouterLink>
        <RouterLink to="/keys">Keys</RouterLink>
        <RouterLink to="/usage">Usage</RouterLink>
        <RouterLink to="/budgets">Budgets</RouterLink>
      </nav>
      <span class="spacer" />
      <button
        class="theme-toggle"
        :title="theme.mode === 'dark' ? 'Switch to light' : 'Switch to dark'"
        :aria-label="theme.mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
        @click="theme.toggle"
      >
        {{ theme.mode === "dark" ? "☀" : "☾" }}
      </button>
      <span v-if="auth.isAuthenticated" class="who">
        {{ auth.principal?.userId }} · {{ auth.principal?.orgId?.slice(0, 8) }}
        <button class="btn btn-secondary" @click="auth.logout">Sign out</button>
      </span>
    </div>
  </header>

  <main>
    <LandingView v-if="!auth.isAuthenticated" />
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
.theme-toggle {
  font: inherit;
  font-size: 15px;
  line-height: 1;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink);
  cursor: pointer;
  transition: border-color 250ms ease;
}
.theme-toggle:hover {
  border-color: var(--text-dim);
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
</style>
