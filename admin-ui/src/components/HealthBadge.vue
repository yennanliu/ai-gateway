<script setup lang="ts">
import { computed } from "vue";
import { healthDisplay } from "@/lib/health";
import { useI18n } from "@/i18n";

const props = defineProps<{ status: string }>();
const { t } = useI18n();
const display = computed(() => healthDisplay(props.status));
const label = computed(() => t(`health.${display.value.tone}`));
</script>

<template>
  <span :class="['badge', display.tone]" role="status">{{ label }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  padding: 0.1rem 0.6rem;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}
.healthy {
  background: var(--moss-soft);
  color: var(--status-go);
}
.degraded {
  background: color-mix(in srgb, var(--status-wait) 15%, transparent);
  color: var(--status-wait);
}
.down {
  background: color-mix(in srgb, var(--status-alert) 12%, transparent);
  color: var(--status-alert);
}
</style>
