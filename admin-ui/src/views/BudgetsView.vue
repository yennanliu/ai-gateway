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
    <h1>{{ $t("budgets.title") }}</h1>
    <div class="card">
      <form class="row" @submit.prevent="submit">
        <select v-model="form.scope_type">
          <option>org</option><option>team</option><option>key</option>
        </select>
        <input v-model="form.scope_id" :placeholder="$t('budgets.scopeId')" required />
        <input v-model="form.limit" :placeholder="$t('budgets.limit')" required />
        <button class="btn btn-primary" type="submit">{{ $t("budgets.set") }}</button>
      </form>
    </div>

    <p v-if="alerts.length" class="pill pill-wait" style="margin-top: 12px">
      {{ $t("budgets.overThreshold", { n: alerts.length }) }}
    </p>

    <div v-if="items.length" class="card" style="margin-top: 16px">
      <table class="data">
        <thead><tr><th>{{ $t("budgets.th.scope") }}</th><th>{{ $t("budgets.th.limit") }}</th><th>{{ $t("budgets.th.spent") }}</th><th>{{ $t("budgets.th.period") }}</th></tr></thead>
        <tbody>
          <tr v-for="b in items" :key="b.id">
            <td>{{ b.scope_type }}:<code>{{ b.scope_id.slice(0, 8) }}</code></td>
            <td>{{ b.limit }}</td>
            <td>{{ b.spent }}</td>
            <td>{{ b.period }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted" style="margin-top: 16px">{{ $t("budgets.empty") }}</p>
  </section>
</template>
