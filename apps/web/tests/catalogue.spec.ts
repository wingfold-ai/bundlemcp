import { test, expect, given, when, then } from "./gherkin";
import { testTitle } from "./spec-map";

// A fresh browser context: this scenario signs in as the dev realm's non-admin
// user (jane), not with the admin session the other tests share.
test.use({ storageState: { cookies: [], origins: [] } });

test(testTitle("E2E-14"), async ({ page, steps }) => {
  await steps.play([
    given("a person without admin rights signs in through Keycloak", { req: "UI-2" }, async () => {
      await page.goto("/servers");
      await page.waitForURL(/(localhost|keycloak):8080/, { timeout: 30_000 });
      await page.locator("#username").fill("jane");
      await page.locator("#password").fill("jane");
      await page.locator("#kc-login").click();
      await page.waitForURL(/\/catalogue/, { timeout: 30_000 });
    }),
    then("they land on the catalogue, with no management navigation", { req: "ADM-3" }, async () => {
      await expect(page.getByTestId("me-email")).toHaveText("jane@example.com");
      await expect(page.getByTestId("catalogue")).toBeVisible();
      await expect(page.getByTestId("nav-servers")).toHaveCount(0);
    }),
    then("the seeded bundles with OAuth endpoints are listed", { req: "API-1" }, async () => {
      for (const name of ["seo", "media"]) {
        await expect(page.getByTestId(`catalogue-bundle-${name}`)).toBeVisible();
      }
      await page.screenshot({ path: "test-results/catalogue-non-admin.png", fullPage: true });
    }),
    when("they open a bundle", () => page.getByTestId("catalogue-bundle-seo").click()),
    then("its endpoints are shown with their connection URLs", { req: "API-1" }, async () => {
      await expect(page.getByTestId("catalogue-seo")).toBeVisible();
      await expect(page.getByTestId("catalogue-url-seo")).toContainText("/seo/mcp");
      await page.screenshot({ path: "test-results/catalogue-bundle-non-admin.png", fullPage: true });
    }),
    when("they try to open a management page", { req: "UI-2" }, async () => {
      await page.goto("/servers");
    }),
    then("they are sent back to the catalogue", { req: "UI-2" }, async () => {
      await page.waitForURL(/\/catalogue/, { timeout: 15_000 });
      await expect(page.getByTestId("catalogue")).toBeVisible();
    }),
  ]);
});
