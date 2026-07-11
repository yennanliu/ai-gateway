import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import { setAuthHeadersProvider, type AuthHeaders } from "@/api/client";

const STORAGE_KEY = "aigw.principal";

export interface DevPrincipal {
  userId: string;
  orgId: string;
  roles: string[];
}

export function principalToHeaders(p: DevPrincipal | null): AuthHeaders {
  if (!p) return {};
  return {
    "X-User-Id": p.userId,
    "X-Org-Id": p.orgId,
    "X-Org-Roles": p.roles.join(","),
  };
}

/** Dev auth: a stand-in principal persisted locally until OIDC lands (M6+). */
export const useAuthStore = defineStore("auth", () => {
  const stored = localStorage.getItem(STORAGE_KEY);
  const principal = ref<DevPrincipal | null>(stored ? JSON.parse(stored) : null);

  const isAuthenticated = computed(() => principal.value !== null);

  function login(p: DevPrincipal): void {
    principal.value = p;
  }

  function logout(): void {
    principal.value = null;
  }

  watch(
    principal,
    (p) => {
      if (p) localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
      else localStorage.removeItem(STORAGE_KEY);
    },
    { immediate: false },
  );

  // Every request carries the current principal's dev headers.
  setAuthHeadersProvider(() => principalToHeaders(principal.value));

  return { principal, isAuthenticated, login, logout };
});
