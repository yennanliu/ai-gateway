<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { budgets } from "@/api/client";
import type { Budget, BudgetAlert } from "@/api/types";

const items = ref<Budget[]>([]);
const alerts = ref<BudgetAlert[]>([]);
const form = reactive({ scope_type: "team", scope_id: "", limit: "" });

async function refresh(): Promise<void> {
  items.value = await budgets.list();
  alerts.value = await budgets.alerts();
}

onMounted(refresh);

async function submit(): Promise<void> {
  await budgets.upsert({ ...form });
  form.scope_id = "";
  form.limit = "";
  await refresh();
}
</script>

<template>
  <section>
    <h1>Budgets</h1>
    <form class="row" @submit.prevent="submit">
      <select v-model="form.scope_type">
        <option>org</option><option>team</option><option>key</option>
      </select>
      <input v-model="form.scope_id" placeholder="scope id" required />
      <input v-model="form.limit" placeholder="limit" required />
      <button type="submit">Set budget</button>
    </form>

    <p v-if="alerts.length" class="alert">
      {{ alerts.length }} budget(s) over threshold
    </p>

    <table v-if="items.length">
      <thead><tr><th>Scope</th><th>Limit</th><th>Spent</th><th>Period</th></tr></thead>
      <tbody>
        <tr v-for="b in items" :key="b.id">
          <td>{{ b.scope_type }}:{{ b.scope_id }}</td>
          <td>{{ b.limit }}</td>
          <td>{{ b.spent }}</td>
          <td>{{ b.period }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No budgets set.</p>
  </section>
</template>

<style scoped>
.row { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.alert { color: #d97706; }
.muted { color: #6b7280; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #e5e7eb; }
</style>
