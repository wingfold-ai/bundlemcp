import { test, expect, given, when, then } from "./gherkin";
import { STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// User administration: listing, the deactivate action, and the consent
// drill-down. The seeded admin is the only account, so the destructive
// Deactivate action is asserted present but never clicked — deactivating it
// would lock the whole suite out.
test(testTitle("E2E-09"), async ({ page, steps }) => {
  // The seeded admin can appear under more than one OIDC subject; assert on the
  // first row (matching E2E-01) rather than a strict single match.
  const row = () => page.getByTestId("user-admin@example.com").first();

  await steps.play([
    given("the users page listing provisioned users with admin flag", { req: "UI-1" }, async () => {
      await page.goto("/users");
      await expect(row()).toBeVisible();
      await expect(row()).toContainText("admin");
    }),
    then("a deactivate action is offered (not clicked — only admin)", { req: "AUTH-20" }, async () => {
      await expect(page.getByTestId("deactivate-user-admin@example.com").first()).toBeEnabled();
    }),
    when("drilling into the user's OAuth consents", { req: "AUTH-11" }, async () => {
      // The toggle label flips deterministically regardless of consent count.
      const toggle = page.getByTestId("consents-admin@example.com").first();
      await toggle.click();
      await expect(toggle).toContainText("Hide consents");
    }),
  ]);
});

// Deactivation is sticky: the dev realm's non-admin user (jane) is signed in once so
// she exists, deactivated by the admin, refused when she signs in again, and
// reactivated. Her own browser context keeps her session apart from the admin's.
test(testTitle("E2E-23"), async ({ page, browser, steps }) => {
  const jane = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const janePage = await jane.newPage();
  const signInAsJane = async () => {
    await janePage.context().clearCookies();
    await janePage.goto("/upstreams");
    await janePage.waitForURL(/(localhost|keycloak):8080/, { timeout: 30_000 });
    await janePage.locator("#username").fill("jane");
    await janePage.locator("#password").fill("jane");
    await janePage.locator("#kc-login").click();
  };
  try {
    await steps.play([
      given("jane has signed in once, so she is a provisioned user", { req: "AUTH-20" }, async () => {
        await signInAsJane();
        await janePage.waitForURL(/\/catalogue/, { timeout: 30_000 });
        await page.goto("/users");
        await expect(page.getByTestId("user-jane@example.com")).toBeVisible();
      }),
      when("the admin deactivates her", { req: "AUTH-20" }, async () => {
        await page.getByTestId("deactivate-user-jane@example.com").click();
        await expect(page.getByTestId("reactivate-user-jane@example.com")).toBeVisible();
      }),
      then("signing in at the identity provider again does not let her in", { req: "AUTH-20" }, async () => {
        await signInAsJane();
        await expect(janePage.getByText("Your account is deactivated")).toBeVisible({
          timeout: 30_000,
        });
      }),
      when("the admin reactivates her", { req: "AUTH-20" }, async () => {
        await page.getByTestId("reactivate-user-jane@example.com").click();
        await expect(page.getByTestId("deactivate-user-jane@example.com")).toBeVisible();
      }),
      then("she can sign in again", { req: "AUTH-20" }, async () => {
        await signInAsJane();
        await janePage.waitForURL(/\/catalogue/, { timeout: 30_000 });
      }),
    ]);
  } finally {
    await jane.close();
  }
});
