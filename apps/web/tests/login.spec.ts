import { test, expect, given, then } from "./gherkin";
import { STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

test(testTitle("E2E-01"), async ({ page, steps }) => {
  await steps.play([
    given("an admin signed in via the real OIDC flow (gateway → Keycloak)", { req: "UI-2" }, async () => {
      await page.goto("/upstreams");
      await expect(page.getByTestId("me-email")).toHaveText("admin@example.com");
    }),
    then("the upstream servers page lists the seeded upstreams with health badges", { req: "UI-1" }, async () => {
      for (const name of ["echo", "oauth-demo"]) {
        await expect(page.getByTestId(`row-${name}`)).toBeVisible();
      }
    }),
    then("each server shows the MCP revision it negotiated, or a dash when unprobed", { req: "UPS-10" }, async () => {
      // echo answers anyone, so its probe completes; oauth-demo is only probed
      // once a user has connected an account to it.
      await expect(page.getByTestId("protocol-echo")).toContainText(/^\d{4}-\d{2}-\d{2}$/);
      await expect(page.getByTestId("protocol-oauth-demo")).toContainText("—");
    }),
  ]);
});

test(testTitle("E2E-02"), async ({ page, steps }) => {
  const stops: Array<[string, string, string]> = [
    ["nav-bundles", "row-demo", "Bundles"],
    ["nav-matrix", "matrix-table", "Composition"],
    ["nav-endpoints", "row-demo", "Endpoints"],
    ["nav-api-keys", "key-create", "API keys"],
    ["nav-users", "user-admin@example.com", "Users"],
    ["nav-audit", "filter-apply", "Audit"],
    ["nav-logs", "logs-placeholder", "Live logs"],
    ["nav-inspector", "inspector-placeholder", "Inspector"],
    ["nav-settings", "config-row-audit_retention_days", "Settings"],
  ];
  await steps.play([
    given("the admin on the servers page", { req: "UI-1" }, () => page.goto("/upstreams")),
    ...stops.map(([nav, marker, label]) =>
      then(`the ${label} page is reachable from the nav`, { req: "UI-1" }, async () => {
        await page.getByTestId(nav).click();
        await expect(page.getByTestId(marker).first()).toBeVisible({ timeout: 15_000 });
      }),
    ),
  ]);
});
