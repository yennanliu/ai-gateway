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
    <h1>{{ $t("models.title") }}</h1>
    <div class="card">
      <form class="row" @submit.prevent="submit">
        <input v-model="form.public_name" :placeholder="$t('models.publicName')" required />
        <input v-model="form.provider" :placeholder="$t('models.provider')" required />
        <input v-model="form.model" :placeholder="$t('models.model')" required />
        <button class="btn btn-primary" type="submit">{{ $t("models.add") }}</button>
      </form>
    </div>

    <p v-if="registry.error" class="pill pill-alert">{{ registry.error }}</p>

    <div v-if="registry.items.length" class="card" style="margin-top: 16px">
      <table class="data">
        <thead>
          <tr>
            <th>{{ $t("models.th.name") }}</th>
            <th>{{ $t("models.th.provider") }}</th>
            <th>{{ $t("models.th.model") }}</th>
            <th>{{ $t("models.th.status") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in registry.items" :key="m.id">
            <td>{{ m.public_name }}</td>
            <td>{{ m.provider }}</td>
            <td><code>{{ m.model }}</code></td>
            <td><span class="pill pill-go">{{ m.status }}</span></td>
            <td>
              <button class="btn btn-secondary" @click="registry.remove(m.id)">
                {{ $t("models.delete") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted" style="margin-top: 16px">{{ $t("models.empty") }}</p>
  </section>
</template>
