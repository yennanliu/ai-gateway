<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { useI18n } from "@/i18n";
import { LOCALES, type Locale } from "@/i18n/messages";
import LandingView from "@/views/LandingView.vue";

const auth = useAuthStore();
const theme = useThemeStore();
const { locale, setLocale } = useI18n();

const langOpen = ref(false);
const langMenu = ref<HTMLElement | null>(null);

function pickLocale(l: Locale): void {
  setLocale(l);
  langOpen.value = false;
}

function onDocClick(e: MouseEvent): void {
  if (langMenu.value && !langMenu.value.contains(e.target as Node)) langOpen.value = false;
}

onMounted(() => document.addEventListener("click", onDocClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocClick));
</script>

<template>
  <header class="topbar">
    <div class="container bar">
      <RouterLink to="/" class="wordmark">AI&nbsp;GATEWAY</RouterLink>
      <nav v-if="auth.isAuthenticated">
        <RouterLink to="/">{{ $t("nav.dashboard") }}</RouterLink>
        <RouterLink to="/models">{{ $t("nav.models") }}</RouterLink>
        <RouterLink to="/teams">{{ $t("nav.teams") }}</RouterLink>
        <RouterLink to="/keys">{{ $t("nav.keys") }}</RouterLink>
        <RouterLink to="/usage">{{ $t("nav.usage") }}</RouterLink>
        <RouterLink to="/budgets">{{ $t("nav.budgets") }}</RouterLink>
        <RouterLink to="/data-plane">{{ $t("nav.dataPlane") }}</RouterLink>
      </nav>
      <span class="spacer" />
      <div ref="langMenu" class="lang">
        <button
          class="icon-toggle"
          :title="$t('app.language')"
          :aria-label="$t('app.language')"
          aria-haspopup="menu"
          :aria-expanded="langOpen"
          @click="langOpen = !langOpen"
        >
          文<sub>A</sub>
        </button>
        <ul v-if="langOpen" class="lang-menu" role="menu">
          <li v-for="l in LOCALES" :key="l.value" role="none">
            <button
              role="menuitemradio"
              :aria-checked="locale === l.value"
              :class="{ active: locale === l.value }"
              @click="pickLocale(l.value)"
            >
              {{ l.label }}
            </button>
          </li>
        </ul>
      </div>
      <button
        class="icon-toggle"
        :title="theme.mode === 'dark' ? $t('app.toLight') : $t('app.toDark')"
        :aria-label="theme.mode === 'dark' ? $t('app.toLight') : $t('app.toDark')"
        @click="theme.toggle"
      >
        {{ theme.mode === "dark" ? "☀" : "☾" }}
      </button>
      <span v-if="auth.isAuthenticated" class="who">
        {{ auth.principal?.userId }} · {{ auth.principal?.orgId?.slice(0, 8) }}
        <button class="btn btn-secondary" @click="auth.logout">{{ $t("app.signOut") }}</button>
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
.icon-toggle {
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
.icon-toggle:hover {
  border-color: var(--text-dim);
}
.icon-toggle sub {
  font-size: 0.7em;
  vertical-align: sub;
}
.lang {
  position: relative;
  display: inline-flex;
}
.lang-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 160px;
  margin: 0;
  padding: 6px;
  list-style: none;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-input, 10px);
  box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
  z-index: 20;
}
.lang-menu button {
  width: 100%;
  text-align: left;
  font: inherit;
  font-size: 15px;
  padding: 0.5rem 0.7rem;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink);
  cursor: pointer;
}
.lang-menu button:hover {
  background: var(--bg-alt);
}
.lang-menu button.active {
  font-weight: 600;
  color: var(--accent);
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
