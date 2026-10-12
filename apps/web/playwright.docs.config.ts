import { defineConfig } from "@playwright/test";

// Screenshots for the documentation site, taken from the running compose stack
// started locally (`TUNNEL=none deploy/stack.sh up`), so every URL in them
// reads localhost. Kept apart from the e2e suite: this run writes into
// docs/public/screenshots/ and creates, then removes, its own resources.
//   cd apps/web && npm run docs:screenshots
export default defineConfig({
  testDir: "./docs-screenshots",
  timeout: 120_000,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.WEB_URL ?? "http://localhost:3000",
    viewport: { width: 1440, height: 900 },
    colorScheme: "light",
  },
  globalSetup: "./tests/global-setup.ts",
});
