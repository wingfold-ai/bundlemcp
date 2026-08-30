import { test, expect, given, then } from "./gherkin";
import { STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

test(testTitle("E2E-01"), async ({ page, steps }) => {
  await steps.play([
    given("an admin signed in via the real OIDC flow (gateway → Keycloak)", { req: "UI-2" }, async () => {
      await page.goto("/servers");
      await expect(page.getByTestId("me-email")).toHaveText("admin@example.com");
    }),
    then("the servers page lists the seeded upstreams with health badges", { req: "UI-1" }, async () => {
      for (const name of ["echo", "seo-psi", "seo-gsc", "dataforseo", "hyperframes"]) {
        await expect(page.getByTestId(`row-${name}`)).toBeVisible();
      }
    }),
  ]);
});

test(testTitle("E2E-02"), async ({ page, steps }) => {
  const stops: Array<[string, string, string]> = [
    ["nav-bundles", "row-seo", "Bundles"],
    ["nav-endpoints", "row-seo", "Endpoints"],
    ["nav-api-keys", "key-create", "API keys"],
    ["nav-users", "user-admin@example.com", "Users"],
    ["nav-audit", "filter-apply", "Audit"],
    ["nav-logs", "logs-placeholder", "Live logs"],
    ["nav-inspector", "inspector-placeholder", "Inspector"],
    ["nav-settings", "config-row-audit_retention_days", "Settings"],
  ];
  await steps.play([
    given("the admin on the servers page", { req: "UI-1" }, () => page.goto("/servers")),
    ...stops.map(([nav, marker, label]) =>
      then(`the ${label} page is reachable from the nav`, { req: "UI-1" }, async () => {
        await page.getByTestId(nav).click();
        await expect(page.getByTestId(marker).first()).toBeVisible({ timeout: 15_000 });
      }),
    ),
  ]);
});
