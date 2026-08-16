import { defineConfig } from "@playwright/test";

/**
 * E2E config — real browser tests, distinct from the Vitest unit
 * suite (vitest.config.ts). Assumes the web app and API are already
 * running (see e2e/README.md) rather than spawning them itself, since
 * a real registration test needs a real, migrated Postgres + Redis
 * behind the API — infrastructure this config has no business owning.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false, // registration tests create real DB rows — avoid cross-test races
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
