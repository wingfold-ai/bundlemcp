import { defineConfig } from "@playwright/test";

// UI integration tests against the running compose stack:
//   docker compose -f deploy/docker-compose.yml up -d --build
//   cd apps/web && npx playwright test
//
// Set PW_VIDEO=1 to record a watchable run (video of every test, plus slow
// motion so the steps are followable). Off by default to keep runs fast:
//   PW_VIDEO=1 npx playwright test
const recording = process.env.PW_VIDEO === "1";

export default defineConfig({
  testDir: "./tests",
  timeout: recording ? 180_000 : 60_000,
  workers: 1, // the stack is stateful; keep flows deterministic
  retries: 0,
  use: {
    baseURL: process.env.WEB_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    viewport: { width: 1280, height: 720 },
    video: recording ? { mode: "on", size: { width: 1280, height: 720 } } : "off",
    launchOptions: recording ? { slowMo: 400 } : {},
  },
  globalSetup: "./tests/global-setup.ts",
});
