<script setup lang="ts">
import { ref } from "vue";
import { useKeysStore } from "@/stores/keys";

const store = useKeysStore();
const teamId = ref("");

async function load(): Promise<void> {
  if (teamId.value) await store.refresh(teamId.value);
}

async function issue(): Promise<void> {
  if (teamId.value) await store.issue(teamId.value);
}
</script>

<template>
  <section>
    <h1>Virtual keys</h1>
    <div class="row">
      <input v-model="teamId" placeholder="team id" />
      <button @click="load">Load</button>
      <button :disabled="!teamId" @click="issue">Issue key</button>
    </div>

    <p v-if="store.lastIssued" class="issued">
      New key (shown once): <code>{{ store.lastIssued.key }}</code>
    </p>

    <table v-if="store.items.length">
      <thead><tr><th>Prefix</th><th>Status</th><th></th></tr></thead>
      <tbody>
        <tr v-for="k in store.items" :key="k.id">
          <td><code>{{ k.prefix }}</code></td>
          <td>{{ k.status }}</td>
          <td>
            <button :disabled="k.status !== 'active'" @click="store.revoke(k.id, teamId)">
              Revoke
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No keys loaded.</p>
  </section>
</template>

<style scoped>
.row { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.issued { background: #f0fdf4; padding: 0.5rem; border-radius: 4px; }
.muted { color: #6b7280; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #e5e7eb; }
</style>
