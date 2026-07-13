<script setup lang="ts">
import { computed, reactive } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useI18n } from "@/i18n";
import { messages } from "@/i18n/messages";

const auth = useAuthStore();
const { locale } = useI18n();
const form = reactive({ userId: "admin", orgId: "", roles: "org-admin" });

function login(): void {
  auth.login({ userId: form.userId, orgId: form.orgId, roles: form.roles.split(",") });
}

const features = computed(() => messages[locale.value].landing.features);
</script>

<template>
  <section class="film">
    <div class="container film-inner">
      <p class="eyebrow">{{ $t("landing.eyebrow") }}</p>
      <h1 class="hero">{{ $t("landing.heroLine1") }}<br />{{ $t("landing.heroLine2") }}</h1>
      <p class="sub muted">{{ $t("landing.sub") }}</p>

      <div class="card signin">
        <p class="muted">{{ $t("landing.signinTitle") }}</p>
        <div class="row">
          <input v-model="form.userId" :placeholder="$t('landing.userId')" />
          <input v-model="form.orgId" :placeholder="$t('landing.orgId')" />
          <input v-model="form.roles" :placeholder="$t('landing.roles')" />
          <button class="btn btn-primary" :disabled="!form.orgId" @click="login">
            {{ $t("landing.enter") }}
          </button>
        </div>
        <p class="hint muted">
          {{ $t("landing.tipPre") }} <code>make seed</code> {{ $t("landing.tipPost") }}
        </p>
      </div>
    </div>
  </section>

  <section class="container features">
    <div class="feature card" v-for="f in features" :key="f.title">
      <h3>{{ f.title }}</h3>
      <p class="muted">{{ f.body }}</p>
    </div>
  </section>
</template>

<style scoped>
.film {
  background:
    radial-gradient(120% 90% at 72% -10%, color-mix(in srgb, var(--accent) 22%, transparent), transparent 60%),
    linear-gradient(180deg, var(--bg-alt), var(--bg));
  display: flex;
  align-items: center;
  padding: 72px 0 48px;
}
.film-inner {
  padding: 24px;
}
.eyebrow {
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 12px;
  color: var(--accent);
  margin: 0 0 0.75rem;
}
.hero {
  font-size: clamp(36px, 6vw, 64px);
  font-weight: 300;
  line-height: 1.05;
  letter-spacing: -0.02em;
  margin: 0 0 1rem;
}
.sub {
  max-width: 560px;
  font-size: 18px;
  margin: 0 0 2rem;
}
.signin {
  max-width: 680px;
}
.signin .row {
  margin-top: 0.75rem;
}
.signin input {
  flex: 1;
  min-width: 140px;
}
.hint {
  margin: 0.75rem 0 0;
  font-size: 13px;
}
.features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 20px;
  padding-top: 24px;
  padding-bottom: 80px;
}
.feature h3 {
  font-size: 18px;
}
.feature p {
  margin: 0;
  font-size: 14px;
}
</style>
