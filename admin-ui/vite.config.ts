import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Dev: forward API calls to the governance-api.
      "/api": "http://localhost:8080",
      // Dev: the data plane's own surfaces go straight to the LiteLLM proxy.
      // (On AWS the ALB path-routes these; locally we proxy them here.)
      "/health": "http://localhost:4000",
      "/v1": "http://localhost:4000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
