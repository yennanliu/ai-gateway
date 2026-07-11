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
    <div class="card">
      <form class="row" @submit.prevent="submit">
        <input v-model="form.public_name" placeholder="public name" required />
        <input v-model="form.provider" placeholder="provider" required />
        <input v-model="form.model" placeholder="model" required />
        <button class="btn btn-primary" type="submit">Add model</button>
      </form>
    </div>

    <p v-if="registry.error" class="pill pill-alert">{{ registry.error }}</p>

    <div v-if="registry.items.length" class="card" style="margin-top: 16px">
      <table class="data">
        <thead>
          <tr><th>Name</th><th>Provider</th><th>Model</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="m in registry.items" :key="m.id">
            <td>{{ m.public_name }}</td>
            <td>{{ m.provider }}</td>
            <td><code>{{ m.model }}</code></td>
            <td><span class="pill pill-go">{{ m.status }}</span></td>
            <td><button class="btn btn-secondary" @click="registry.remove(m.id)">Delete</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted" style="margin-top: 16px">No models yet.</p>
  </section>
</template>
