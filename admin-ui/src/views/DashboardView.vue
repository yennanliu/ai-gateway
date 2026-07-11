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
    <p class="muted">
      Governance API <HealthBadge :status="health.status" />
    </p>

    <div class="stat-grid">
      <div class="stat">
        <span class="label">Total cost</span>
        <span class="value">${{ usage.totalCost.toFixed(2) }}</span>
      </div>
      <div class="stat">
        <span class="label">Requests</span>
        <span class="value">{{ usage.totalRequests }}</span>
      </div>
      <div class="stat">
        <span class="label">Budget alerts</span>
        <span class="value">{{ alertCount }}</span>
      </div>
    </div>
  </section>
</template>
