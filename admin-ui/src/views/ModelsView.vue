<script setup lang="ts">
import { onMounted, reactive } from "vue";
import { useRegistryStore } from "@/stores/registry";

const registry = useRegistryStore();
const form = reactive({ public_name: "", provider: "openai", model: "" });

onMounted(() => registry.refresh());

async function submit(): Promise<void> {
  await registry.create({ ...form });
  form.public_name = "";
  form.model = "";
}
</script>

<template>
  <section>
    <h1>Model registry</h1>
    <form class="row" @submit.prevent="submit">
      <input v-model="form.public_name" placeholder="public name" required />
      <input v-model="form.provider" placeholder="provider" required />
      <input v-model="form.model" placeholder="model" required />
      <button type="submit">Add model</button>
    </form>
    <p v-if="registry.error" class="error">{{ registry.error }}</p>
    <table v-if="registry.items.length">
      <thead>
        <tr><th>Name</th><th>Provider</th><th>Model</th><th>Status</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="m in registry.items" :key="m.id">
          <td>{{ m.public_name }}</td>
          <td>{{ m.provider }}</td>
          <td>{{ m.model }}</td>
          <td>{{ m.status }}</td>
          <td><button @click="registry.remove(m.id)">Delete</button></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No models yet.</p>
  </section>
</template>

<style scoped>
.row { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.error { color: #dc2626; }
.muted { color: #6b7280; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #e5e7eb; }
</style>
