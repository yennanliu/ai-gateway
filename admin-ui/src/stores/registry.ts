import { defineStore } from "pinia";
import { ref } from "vue";
import { models } from "@/api/client";
import type { ModelDeployment } from "@/api/types";

export const useRegistryStore = defineStore("registry", () => {
  const items = ref<ModelDeployment[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function refresh(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      items.value = await models.list();
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function create(body: Partial<ModelDeployment>): Promise<void> {
    await models.create(body);
    await refresh();
  }

  async function remove(id: string): Promise<void> {
    await models.remove(id);
    items.value = items.value.filter((m) => m.id !== id);
  }

  return { items, loading, error, refresh, create, remove };
});
