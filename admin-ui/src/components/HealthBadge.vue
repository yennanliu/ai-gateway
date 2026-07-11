<script setup lang="ts">
import { computed } from "vue";
import { healthDisplay } from "@/lib/health";

const props = defineProps<{ status: string }>();
const display = computed(() => healthDisplay(props.status));
</script>

<template>
  <span :class="['badge', display.tone]" role="status">{{ display.label }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
  color: #fff;
}
.healthy {
  background: #16a34a;
}
.degraded {
  background: #d97706;
}
.down {
  background: #dc2626;
}
</style>
