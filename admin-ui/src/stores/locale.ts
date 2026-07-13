import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { HTML_LANG, type Locale } from "@/i18n/messages";

const STORAGE_KEY = "aigw.locale";

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "zh-TW") return saved;
  } catch {
    // localStorage disabled/restricted (private mode, sandboxed iframe) — fall through.
  }
  // Fall back to the browser preference: any zh-Hant/zh-TW/zh-HK reader gets Traditional Chinese.
  const nav = navigator.language ?? "";
  if (/^zh\b/i.test(nav) && !/hans|cn|sg/i.test(nav)) return "zh-TW";
  return "en";
}

function apply(locale: Locale): void {
  document.documentElement.lang = HTML_LANG[locale];
}

/** UI language with a manual toggle, persisted and reflected on <html lang>. */
export const useLocaleStore = defineStore("locale", () => {
  const locale = ref<Locale>(initialLocale());
  apply(locale.value);

  function setLocale(next: Locale): void {
    locale.value = next;
  }

  watch(locale, (l) => {
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // Persistence failed (quota/restricted) — the choice still applies for this session.
    }
    apply(l);
  });

  return { locale, setLocale };
});
