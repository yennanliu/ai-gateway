<script setup lang="ts">
import { onMounted } from "vue";
import { useUsageStore } from "@/stores/usage";

const store = useUsageStore();
onMounted(() => store.refresh("model"));
</script>

<template>
  <section>
    <h1>{{ $t("usage.title") }}</h1>
    <div class="stat-grid">
      <div class="stat">
        <span class="label">{{ $t("common.totalCost") }}</span>
        <span class="value">${{ store.totalCost.toFixed(2) }}</span>
      </div>
      <div class="stat">
        <span class="label">{{ $t("common.requests") }}</span>
        <span class="value">{{ store.totalRequests }}</span>
      </div>
    </div>

    <div v-if="store.rows.length" class="card" style="margin-top: 16px">
      <table class="data">
        <thead>
          <tr>
            <th>{{ $t("usage.th.model") }}</th>
            <th>{{ $t("usage.th.prompt") }}</th>
            <th>{{ $t("usage.th.completion") }}</th>
            <th>{{ $t("usage.th.cost") }}</th>
            <th>{{ $t("usage.th.requests") }}</th>
          </tr>
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
    </div>
    <p v-else class="muted" style="margin-top: 16px">{{ $t("usage.empty") }}</p>
  </section>
</template>
