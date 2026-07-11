import { createRouter, createWebHistory } from "vue-router";
import DashboardView from "@/views/DashboardView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: DashboardView },
    { path: "/models", name: "models", component: () => import("@/views/ModelsView.vue") },
    { path: "/teams", name: "teams", component: () => import("@/views/TeamsView.vue") },
    { path: "/keys", name: "keys", component: () => import("@/views/KeysView.vue") },
    { path: "/usage", name: "usage", component: () => import("@/views/UsageView.vue") },
    { path: "/budgets", name: "budgets", component: () => import("@/views/BudgetsView.vue") },
  ],
});
