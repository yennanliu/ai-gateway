import { defineStore } from "pinia";
import { ref } from "vue";
import { keys } from "@/api/client";
import type { KeyIssued, VirtualKey } from "@/api/types";

export const useKeysStore = defineStore("keys", () => {
  const items = ref<VirtualKey[]>([]);
  const lastIssued = ref<KeyIssued | null>(null);

  async function refresh(teamId: string): Promise<void> {
    items.value = await keys.list(teamId);
  }

  async function issue(teamId: string, allowedModels: string[] = []): Promise<KeyIssued> {
    const issued = await keys.issue({ team_id: teamId, allowed_models: allowedModels });
    lastIssued.value = issued;
    await refresh(teamId);
    return issued;
  }

  async function revoke(id: string, teamId: string): Promise<void> {
    await keys.revoke(id);
    await refresh(teamId);
  }

  return { items, lastIssued, refresh, issue, revoke };
});
