import { defineStore } from "pinia";
import { ref } from "vue";
import { teams } from "@/api/client";
import type { Team } from "@/api/types";

export const useTeamsStore = defineStore("teams", () => {
  const items = ref<Team[]>([]);
  const error = ref<string | null>(null);

  async function refresh(orgId: string): Promise<void> {
    error.value = null;
    try {
      items.value = await teams.list(orgId);
    } catch (e) {
      error.value = (e as Error).message;
    }
  }

  async function create(orgId: string, name: string): Promise<void> {
    await teams.create(orgId, name);
    await refresh(orgId);
  }

  return { items, error, refresh, create };
});
