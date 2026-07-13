<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useTeamsStore } from "@/stores/teams";

const auth = useAuthStore();
const store = useTeamsStore();
const name = ref("");

const orgId = () => auth.principal?.orgId ?? "";

onMounted(() => store.refresh(orgId()));

async function submit(): Promise<void> {
  if (!name.value) return;
  await store.create(orgId(), name.value);
  name.value = "";
}
</script>

<template>
  <section>
    <h1>{{ $t("teams.title") }}</h1>
    <div class="card">
      <form class="row" @submit.prevent="submit">
        <input v-model="name" :placeholder="$t('teams.name')" required />
        <button class="btn btn-primary" type="submit">{{ $t("teams.create") }}</button>
      </form>
    </div>

    <p v-if="store.error" class="pill pill-alert" style="margin-top: 12px">{{ store.error }}</p>

    <div v-if="store.items.length" class="card" style="margin-top: 16px">
      <table class="data">
        <thead><tr><th>{{ $t("teams.th.name") }}</th><th>{{ $t("teams.th.id") }}</th></tr></thead>
        <tbody>
          <tr v-for="t in store.items" :key="t.id">
            <td>{{ t.name }}</td>
            <td><code>{{ t.id }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted" style="margin-top: 16px">{{ $t("teams.empty") }}</p>
  </section>
</template>
