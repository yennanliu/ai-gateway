import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { usage } from "@/api/client";
import type { UsageRow } from "@/api/types";

export const useUsageStore = defineStore("usage", () => {
  const rows = ref<UsageRow[]>([]);

  const totalCost = computed(() =>
    rows.value.reduce((sum, r) => sum + Number(r.cost), 0),
  );
  const totalRequests = computed(() =>
    rows.value.reduce((sum, r) => sum + r.requests, 0),
  );

  async function refresh(groupBy = "model"): Promise<void> {
    rows.value = await usage.summary(groupBy);
  }

  return { rows, totalCost, totalRequests, refresh };
});
