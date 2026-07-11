import { defineStore } from "pinia";
import { ref, watch } from "vue";

export type ThemeMode = "light" | "dark";
const STORAGE_KEY = "aigw.theme";

function initialMode(): ThemeMode {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  return prefersDark ? "dark" : "light";
}

function apply(mode: ThemeMode): void {
  document.documentElement.dataset.theme = mode;
}

/** Light/dark theme with a manual toggle, persisted and applied to <html>. */
export const useThemeStore = defineStore("theme", () => {
  const mode = ref<ThemeMode>(initialMode());
  apply(mode.value);

  function toggle(): void {
    mode.value = mode.value === "dark" ? "light" : "dark";
  }

  watch(mode, (m) => {
    localStorage.setItem(STORAGE_KEY, m);
    apply(m);
  });

  return { mode, toggle };
});
