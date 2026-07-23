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
    then("a deactivate action is offered (not clicked — only admin)", { req: "ADM-6" }, async () => {
      await expect(page.getByTestId("deactivate-user-admin@example.com").first()).toBeEnabled();
    }),
    when("drilling into the user's OAuth consents", { req: "OAS-11" }, async () => {
      // The toggle label flips deterministically regardless of consent count.
      const toggle = page.getByTestId("consents-admin@example.com").first();
      await toggle.click();
      await expect(toggle).toContainText("Hide consents");
    }),
  ]);
});
