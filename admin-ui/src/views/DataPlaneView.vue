<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import HealthBadge from "@/components/HealthBadge.vue";
import { dataPlane } from "@/api/client";
import type { DataPlaneStatus } from "@/api/types";

const status = ref<DataPlaneStatus | null>(null);
const liveness = ref<{ ok: boolean; detail: string } | null>(null);
const readiness = ref<{ ok: boolean; status: string; db: string } | null>(null);
const error = ref<string | null>(null);

const play = reactive({ key: "", model: "", prompt: "", sending: false, result: "" });

async function refresh(): Promise<void> {
  error.value = null;
  // Health probes self-heal (they never throw), so render them independently of
  // the control-plane status() call — a failing status() must not blank the badges.
  const [live, ready] = await Promise.all([dataPlane.liveness(), dataPlane.readiness()]);
  liveness.value = live;
  readiness.value = ready;
  try {
    const s = await dataPlane.status();
    status.value = s;
    if (!play.model && s.models.length) play.model = s.models[0].model_name;
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function send(): Promise<void> {
  play.sending = true;
  play.result = "";
  try {
    const res = await dataPlane.chat(play.key.trim(), play.model, play.prompt);
    // Pretty-print JSON when possible; fall back to the raw body.
    try {
      play.result = JSON.stringify(JSON.parse(res.body), null, 2);
    } catch {
      play.result = res.body;
    }
    if (!res.ok) play.result = `HTTP ${res.status}\n${play.result}`;
  } catch (e) {
    play.result = (e as Error).message;
  } finally {
    play.sending = false;
  }
}

onMounted(refresh);
</script>

<template>
  <section>
    <h1>{{ $t("dataPlane.title") }}</h1>
    <p class="muted">{{ $t("dataPlane.subtitle") }}</p>

    <p v-if="error" class="pill pill-alert">{{ error }}</p>

    <!-- Live health of the LiteLLM proxy (polled from its own /health/*). -->
    <div class="card status-grid">
      <div class="stat">
        <span class="stat-label">{{ $t("dataPlane.liveness") }}</span>
        <HealthBadge :status="liveness?.ok ? 'healthy' : 'down'" />
        <span v-if="liveness" class="muted mono">{{ liveness.detail }}</span>
      </div>
      <div class="stat">
        <span class="stat-label">{{ $t("dataPlane.readiness") }}</span>
        <HealthBadge :status="readiness?.status ?? 'down'" />
        <span v-if="readiness" class="muted mono">db: {{ readiness.db }}</span>
      </div>
      <div class="stat">
        <span class="stat-label">{{ $t("dataPlane.litellmVersion") }}</span>
        <code>{{ status?.litellm_version ?? "—" }}</code>
      </div>
      <div class="stat">
        <span class="stat-label">{{ $t("dataPlane.routing") }}</span>
        <span class="mono">
          {{ $t("dataPlane.strategy") }}: {{ status?.routing?.routing_strategy ?? "—" }} ·
          {{ $t("dataPlane.retries") }}: {{ status?.routing?.num_retries ?? "—" }}
        </span>
      </div>
    </div>

    <!-- Effective model_list the data plane serves (compiled from the registry). -->
    <h2 class="section">{{ $t("dataPlane.modelsTitle") }}</h2>
    <div v-if="status && status.models.length" class="card">
      <table class="data">
        <thead>
          <tr>
            <th>{{ $t("dataPlane.th.name") }}</th>
            <th>{{ $t("dataPlane.th.provider") }}</th>
            <th>{{ $t("dataPlane.th.model") }}</th>
            <th>{{ $t("dataPlane.th.tags") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in status.models" :key="m.model_name">
            <td>{{ m.model_name }}</td>
            <td>{{ m.provider }}</td>
            <td><code>{{ m.model }}</code></td>
            <td>
              <span v-for="tag in m.tags" :key="tag" class="pill pill-go">{{ tag }}</span>
              <span v-if="!m.tags.length" class="muted">{{ $t("dataPlane.none") }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted">{{ $t("dataPlane.emptyModels") }}</p>

    <!-- Playground: a real /v1 request authed by a virtual key. -->
    <h2 class="section">{{ $t("dataPlane.playground.title") }}</h2>
    <p class="muted">{{ $t("dataPlane.playground.subtitle") }}</p>
    <div class="card">
      <p v-if="status && !status.models.length" class="muted">
        {{ $t("dataPlane.playground.noModels") }}
      </p>
      <form v-else class="play" @submit.prevent="send">
        <label>
          {{ $t("dataPlane.playground.key") }}
          <input v-model="play.key" :placeholder="$t('dataPlane.playground.keyPlaceholder')" required />
        </label>
        <label>
          {{ $t("dataPlane.playground.model") }}
          <select v-model="play.model" required>
            <option v-for="m in status?.models ?? []" :key="m.model_name" :value="m.model_name">
              {{ m.model_name }}
            </option>
          </select>
        </label>
        <label>
          {{ $t("dataPlane.playground.prompt") }}
          <textarea
            v-model="play.prompt"
            rows="3"
            :placeholder="$t('dataPlane.playground.promptPlaceholder')"
            required
          />
        </label>
        <button class="btn btn-primary" type="submit" :disabled="play.sending">
          {{ play.sending ? $t("dataPlane.playground.sending") : $t("dataPlane.playground.send") }}
        </button>
      </form>
      <template v-if="play.result">
        <h3 class="section">{{ $t("dataPlane.playground.response") }}</h3>
        <pre class="result">{{ play.result }}</pre>
      </template>
    </div>
  </section>
</template>

<style scoped>
.section {
  margin: 28px 0 12px;
  font-size: 16px;
}
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
}
.stat {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}
.stat-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
.play {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.play label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
}
.result {
  margin: 0;
  padding: 14px;
  border-radius: 10px;
  background: var(--bg-alt);
  overflow-x: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
