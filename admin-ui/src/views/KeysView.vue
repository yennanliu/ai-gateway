<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useKeysStore } from "@/stores/keys";
import { useTeamsStore } from "@/stores/teams";

const auth = useAuthStore();
const store = useKeysStore();
const teamsStore = useTeamsStore();
const teamId = ref("");
const error = ref<string | null>(null);

onMounted(async () => {
  await teamsStore.refresh(auth.principal?.orgId ?? "");
  if (teamsStore.items.length) teamId.value = teamsStore.items[0].id;
});

watch(teamId, (id) => {
  if (id) void load();
});

async function run(fn: () => Promise<unknown>): Promise<void> {
  error.value = null;
  try {
    await fn();
  } catch (e) {
    error.value = (e as Error).message;
  }
}

const load = () => run(() => store.refresh(teamId.value));
const issue = () => run(() => store.issue(teamId.value));
const revoke = (id: string) => run(() => store.revoke(id, teamId.value));
</script>

<template>
  <section>
    <h1>{{ $t("keys.title") }}</h1>

    <div v-if="!teamsStore.items.length" class="card">
      <p class="muted">
        {{ $t("keys.noTeamsPre") }} <RouterLink to="/teams">{{ $t("keys.teamsLink") }}</RouterLink>
        {{ $t("keys.noTeamsPost") }}
      </p>
    </div>

    <div v-else class="card">
      <div class="row">
        <label class="muted">{{ $t("keys.team") }}</label>
        <select v-model="teamId">
          <option v-for="t in teamsStore.items" :key="t.id" :value="t.id">
            {{ t.name }}
          </option>
        </select>
        <button class="btn btn-primary" :disabled="!teamId" @click="issue">
          {{ $t("keys.issue") }}
        </button>
      </div>
      <p v-if="store.lastIssued" class="issued">
        {{ $t("keys.newKey") }} <code>{{ store.lastIssued.key }}</code>
      </p>
    </div>

    <p v-if="error" class="pill pill-alert" style="margin-top: 12px">{{ error }}</p>

    <div v-if="store.items.length" class="card" style="margin-top: 16px">
      <table class="data">
        <thead><tr><th>{{ $t("keys.th.prefix") }}</th><th>{{ $t("keys.th.status") }}</th><th></th></tr></thead>
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
                @click="revoke(k.id)"
              >
                {{ $t("keys.revoke") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else-if="teamsStore.items.length" class="muted" style="margin-top: 16px">
      {{ $t("keys.empty") }}
    </p>
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
