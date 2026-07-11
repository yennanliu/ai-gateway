<script setup lang="ts">
import { onMounted } from "vue";
import { useUsageStore } from "@/stores/usage";

const store = useUsageStore();
onMounted(() => store.refresh("model"));
</script>

<template>
  <section>
    <h1>Usage</h1>
    <div class="tiles">
      <div class="tile"><span>Total cost</span><strong>${{ store.totalCost.toFixed(2) }}</strong></div>
      <div class="tile"><span>Requests</span><strong>{{ store.totalRequests }}</strong></div>
    </div>
    <table v-if="store.rows.length">
      <thead>
        <tr><th>Model</th><th>Prompt</th><th>Completion</th><th>Cost</th><th>Requests</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in store.rows" :key="r.group ?? 'none'">
          <td>{{ r.group }}</td>
          <td>{{ r.prompt_tokens }}</td>
          <td>{{ r.completion_tokens }}</td>
          <td>${{ Number(r.cost).toFixed(4) }}</td>
          <td>{{ r.requests }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No usage yet.</p>
  </section>
</template>

<style scoped>
.tiles { display: flex; gap: 1rem; margin-bottom: 1rem; }
.tile { border: 1px solid #e5e7eb; border-radius: 6px; padding: 0.75rem 1rem; display: flex; flex-direction: column; }
.tile span { color: #6b7280; font-size: 0.8rem; }
.muted { color: #6b7280; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #e5e7eb; }
</style>
