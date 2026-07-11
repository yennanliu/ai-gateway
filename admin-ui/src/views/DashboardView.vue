<script setup lang="ts">
import { onMounted } from "vue";
import { useHealthStore } from "@/stores/health";
import HealthBadge from "@/components/HealthBadge.vue";

const health = useHealthStore();
onMounted(() => health.refresh());
</script>

<template>
  <section>
    <h1>Dashboard</h1>
    <p>
      Governance API: <HealthBadge :status="health.status" />
    </p>
    <p class="muted">Usage, cost, keys, and model registry views land in M5–M6.</p>
  </section>
</template>

<style scoped>
.muted {
  color: #6b7280;
}
</style>
