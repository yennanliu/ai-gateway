<script setup lang="ts">
import { RouterView } from "vue-router";
</script>

<template>
  <header class="topbar">
    <strong>AI Gateway</strong>
    <span class="tag">Admin</span>
  </header>
  <main class="content">
    <RouterView />
  </main>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #e5e7eb;
}
.tag {
  font-size: 0.75rem;
  color: #6b7280;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  padding: 0 0.35rem;
}
.content {
  padding: 1rem;
}
</style>
