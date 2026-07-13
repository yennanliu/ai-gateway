import { beforeEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { translate } from "@/i18n";
import { useLocaleStore } from "@/stores/locale";

beforeEach(() => {
  localStorage.clear();
  setActivePinia(createPinia());
});

describe("translate", () => {
  it("resolves dotted keys per locale", () => {
    expect(translate("en", "nav.dashboard")).toBe("Dashboard");
    expect(translate("zh-TW", "nav.dashboard")).toBe("儀表板");
  });

  it("interpolates named params", () => {
    expect(translate("en", "budgets.overThreshold", { n: 3 })).toBe("3 budget(s) over threshold");
    expect(translate("zh-TW", "budgets.overThreshold", { n: 3 })).toBe("3 筆預算已超過門檻");
  });

  it("falls back to the key itself when missing", () => {
    expect(translate("en", "nope.missing")).toBe("nope.missing");
  });
});

describe("locale store", () => {
  it("persists the choice and reflects it on <html lang>", async () => {
    const store = useLocaleStore();
    expect(store.locale).toBe("en");
    store.setLocale("zh-TW");
    await nextTick();
    expect(localStorage.getItem("aigw.locale")).toBe("zh-TW");
    expect(document.documentElement.lang).toBe("zh-Hant");
  });
});
