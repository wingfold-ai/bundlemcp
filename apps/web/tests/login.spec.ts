import { test, expect } from "@playwright/test";

test.use({ storageState: "tests/.auth/admin.json" });

test("signed-in admin sees the seeded servers (UI-1/UI-2)", async ({ page }) => {
  await page.goto("/servers");
  await expect(page.getByTestId("me-email")).toHaveText("admin@example.com");
  for (const name of ["echo", "seo-psi", "seo-gsc", "dataforseo", "hyperframes"]) {
    await expect(page.getByTestId(`row-${name}`)).toBeVisible();
  }
});

test("navigation reaches every page (UI-1)", async ({ page }) => {
  await page.goto("/servers");
  const stops: Array<[string, string]> = [
    ["nav-bundles", "row-seo"],
    ["nav-endpoints", "row-seo"],
    ["nav-api-keys", "key-create"],
    ["nav-users", "user-admin@example.com"],
    ["nav-audit", "filter-apply"],
    ["nav-logs", "logs-placeholder"],
    ["nav-inspector", "inspector-placeholder"],
    ["nav-settings", "config-row-audit_retention_days"],
  ];
  for (const [nav, marker] of stops) {
    await page.getByTestId(nav).click();
    await expect(page.getByTestId(marker).first()).toBeVisible({ timeout: 15_000 });
  }
});
