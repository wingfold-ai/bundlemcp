import { defineConfig } from "@playwright/test";

// UI integration tests against the running compose stack:
//   docker compose -f deploy/docker-compose.yml up -d --build
//   cd apps/web && npx playwright test
export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  workers: 1, // the stack is stateful; keep flows deterministic
  retries: 0,
  use: {
    baseURL: process.env.WEB_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  globalSetup: "./tests/global-setup.ts",
});
