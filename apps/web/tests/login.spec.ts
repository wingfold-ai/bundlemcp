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
    then("the servers page lists the seeded upstreams with health badges", { req: "UI-1" }, async () => {
      for (const name of ["echo", "seo-psi", "seo-gsc", "dataforseo", "hyperframes"]) {
        await expect(page.getByTestId(`row-${name}`)).toBeVisible();
      }
    }),
    then("each server shows the MCP revision it negotiated, or a dash when unprobed", { req: "SRV-10" }, async () => {
      // echo is the only seeded upstream the core stack actually runs, so it is
      // the only one that has completed a probe.
      await expect(page.getByTestId("protocol-echo")).toContainText(/^\d{4}-\d{2}-\d{2}$/);
      await expect(page.getByTestId("protocol-seo-psi")).toContainText("—");
    }),
  ]);
});

test(testTitle("E2E-02"), async ({ page, steps }) => {
  const stops: Array<[string, string, string]> = [
    ["nav-bundles", "row-seo", "Bundles"],
    ["nav-matrix", "matrix-table", "Composition"],
    ["nav-endpoints", "row-seo", "Endpoints"],
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
