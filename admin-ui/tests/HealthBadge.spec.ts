import { beforeEach, describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import HealthBadge from "@/components/HealthBadge.vue";
import { healthDisplay } from "@/lib/health";

beforeEach(() => {
  localStorage.clear();
  setActivePinia(createPinia());
});

describe("healthDisplay", () => {
  it("maps ok/ready/healthy to Healthy", () => {
    for (const s of ["ok", "ready", "HEALTHY"]) {
      expect(healthDisplay(s)).toEqual({ label: "Healthy", tone: "healthy" });
    }
  });

  it("maps degraded", () => {
    expect(healthDisplay("degraded").tone).toBe("degraded");
  });

  it("maps unknown/empty to Down", () => {
    expect(healthDisplay("").tone).toBe("down");
    expect(healthDisplay("nope").label).toBe("Down");
  });
});

describe("HealthBadge", () => {
  it("renders the mapped label for a status", () => {
    const wrapper = mount(HealthBadge, {
      props: { status: "ok" },
      global: { plugins: [createPinia()] },
    });
    expect(wrapper.text()).toBe("Healthy");
    expect(wrapper.classes()).toContain("healthy");
  });
});
