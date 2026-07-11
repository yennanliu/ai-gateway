<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useHealthStore } from "@/stores/health";
import { useUsageStore } from "@/stores/usage";
import { budgets } from "@/api/client";
import HealthBadge from "@/components/HealthBadge.vue";

const health = useHealthStore();
const usage = useUsageStore();
const alertCount = ref(0);

onMounted(async () => {
  await health.refresh();
  try {
    await usage.refresh();
    alertCount.value = (await budgets.alerts()).length;
  } catch {
    // usage/budgets require auth; ignore on the dashboard.
  }
});
</script>

<template>
  <section>
    <h1>Dashboard</h1>
    <p>Governance API: <HealthBadge :status="health.status" /></p>
    <div class="tiles">
      <div class="tile"><span>Total cost</span><strong>${{ usage.totalCost.toFixed(2) }}</strong></div>
      <div class="tile"><span>Requests</span><strong>{{ usage.totalRequests }}</strong></div>
      <div class="tile"><span>Budget alerts</span><strong>{{ alertCount }}</strong></div>
    </div>
  </section>
</template>

<style scoped>
.tiles { display: flex; gap: 1rem; margin-top: 1rem; }
.tile { border: 1px solid #e5e7eb; border-radius: 6px; padding: 0.75rem 1rem; display: flex; flex-direction: column; }
.tile span { color: #6b7280; font-size: 0.8rem; }
</style>
