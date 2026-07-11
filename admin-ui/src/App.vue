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
    <strong>AI Gateway</strong>
    <nav>
      <RouterLink to="/">Dashboard</RouterLink>
      <RouterLink to="/models">Models</RouterLink>
      <RouterLink to="/keys">Keys</RouterLink>
      <RouterLink to="/usage">Usage</RouterLink>
      <RouterLink to="/budgets">Budgets</RouterLink>
    </nav>
    <span class="spacer" />
    <span v-if="auth.isAuthenticated" class="who">
      {{ auth.principal?.userId }} · {{ auth.principal?.orgId }}
      <button @click="auth.logout">Sign out</button>
    </span>
  </header>

  <main class="content">
    <div v-if="!auth.isAuthenticated" class="devlogin">
      <p class="muted">Dev sign-in (stand-in until OIDC):</p>
      <input v-model="form.userId" placeholder="user id" />
      <input v-model="form.orgId" placeholder="org id" />
      <input v-model="form.roles" placeholder="roles (comma)" />
      <button :disabled="!form.orgId" @click="login">Sign in</button>
    </div>
    <RouterView v-else />
  </main>
</template>

<style scoped>
.topbar { display: flex; align-items: center; gap: 1rem; padding: 0.75rem 1rem; border-bottom: 1px solid #e5e7eb; }
nav { display: flex; gap: 0.75rem; }
nav a { text-decoration: none; color: #2563eb; }
nav a.router-link-active { font-weight: 600; }
.spacer { flex: 1; }
.who { font-size: 0.85rem; color: #374151; display: flex; gap: 0.5rem; align-items: center; }
.content { padding: 1rem; }
.devlogin { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.muted { color: #6b7280; }
</style>
