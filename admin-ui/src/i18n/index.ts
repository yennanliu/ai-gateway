import { computed, type App } from "vue";
import { useLocaleStore } from "@/stores/locale";
import { messages, type Locale } from "@/i18n/messages";

export type TParams = Record<string, string | number>;

function lookup(locale: Locale, key: string): string | undefined {
  const value = key.split(".").reduce<unknown>((node, part) => {
    if (node && typeof node === "object" && part in node) {
      return (node as Record<string, unknown>)[part];
    }
    return undefined;
  }, messages[locale]);
  return typeof value === "string" ? value : undefined;
}

/** Resolve a dotted key for a locale, falling back to English then the key itself. */
export function translate(locale: Locale, key: string, params?: TParams): string {
  const raw = lookup(locale, key) ?? lookup("en", key) ?? key;
  if (!params) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, name: string) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : `{${name}}`,
  );
}

/** Composable for use in <script setup>. `t` is reactive to the active locale. */
export function useI18n() {
  const store = useLocaleStore();
  const t = (key: string, params?: TParams): string => translate(store.locale, key, params);
  const locale = computed(() => store.locale);
  return { t, locale, setLocale: store.setLocale };
}

/** Install a reactive global `$t` so templates can translate without importing. */
export const i18n = {
  install(app: App): void {
    app.config.globalProperties.$t = (key: string, params?: TParams): string =>
      translate(useLocaleStore().locale, key, params);
  },
};

declare module "vue" {
  interface ComponentCustomProperties {
    $t: (key: string, params?: TParams) => string;
  }
}
