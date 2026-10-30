import { defineVitestConfig } from "@nuxt/test-utils/config";

// Unit tests for the UI's pure logic, kept in unit/: Playwright collects every
// test file under tests/, and Nuxt auto-imports every top-level file in
// app/utils and app/composables, so neither may hold them. A file named
// *.nuxt.test.ts runs inside a Nuxt app (for useQuery, invalidate and the
// composables built on them); every other test runs in plain Node.
export default defineVitestConfig({
  test: {
    include: ["unit/**/*.test.ts"],
    environment: "node",
  },
});
