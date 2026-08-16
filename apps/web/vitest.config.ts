import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // e2e/ uses @playwright/test's own runner (see playwright.config.ts,
    // apps/web/e2e/README.md) — Vitest's default glob would otherwise
    // also try to collect those files and fail, since they use a
    // different, incompatible test() API.
    exclude: ["**/node_modules/**", "e2e/**"],
    coverage: {
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
    },
  },
});
