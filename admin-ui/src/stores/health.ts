import { defineStore } from "pinia";
import { ref } from "vue";

/** Health of the governance API, polled from /healthz. */
export const useHealthStore = defineStore("health", () => {
  const status = ref<string>("unknown");

  async function refresh(fetchImpl: typeof fetch = fetch): Promise<void> {
    try {
      const resp = await fetchImpl("/healthz");
      const body = (await resp.json()) as { status?: string };
      status.value = body.status ?? "down";
    } catch {
      status.value = "down";
    }
  }

  return { status, refresh };
});
