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
    <div class="card">
      <div class="row">
        <input v-model="teamId" placeholder="team id" />
        <button class="btn btn-secondary" @click="load">Load</button>
        <button class="btn btn-primary" :disabled="!teamId" @click="issue">Issue key</button>
      </div>
      <p v-if="store.lastIssued" class="issued">
        New key (shown once): <code>{{ store.lastIssued.key }}</code>
      </p>
    </div>

    <div v-if="store.items.length" class="card" style="margin-top: 16px">
      <table class="data">
        <thead><tr><th>Prefix</th><th>Status</th><th></th></tr></thead>
        <tbody>
          <tr v-for="k in store.items" :key="k.id">
            <td><code>{{ k.prefix }}</code></td>
            <td>
              <span class="pill" :class="k.status === 'active' ? 'pill-go' : 'pill-alert'">
                {{ k.status }}
              </span>
            </td>
            <td>
              <button
                class="btn btn-secondary"
                :disabled="k.status !== 'active'"
                @click="store.revoke(k.id, teamId)"
              >
                Revoke
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted" style="margin-top: 16px">No keys loaded.</p>
  </section>
</template>

<style scoped>
.issued {
  margin-top: 1rem;
  padding: 0.6rem 0.8rem;
  border-radius: var(--radius-input);
  background: var(--moss-soft);
  color: var(--status-go);
}
</style>
