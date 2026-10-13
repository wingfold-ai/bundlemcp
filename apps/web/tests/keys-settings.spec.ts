import { test, expect, given, when, then } from "./gherkin";
import { STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

test(testTitle("E2E-10"), async ({ page, steps }) => {
  const name = "e2e-key";
  page.on("dialog", (d) => d.accept());

  await steps.play([
    given("the admin on the API keys page", () => page.goto("/api-keys")),
    when(`creating key "${name}"`, { req: "AUTH-22" }, async () => {
      await page.getByTestId("key-name").fill(name);
      await page.getByTestId("key-create").click();
    }),
    then("the key value is displayed exactly once", { req: "AUTH-22" }, async () => {
      const value = await page.getByTestId("created-key-value").textContent();
      expect(value).toContain("bmcp_sk_");
      await expect(page.getByTestId(`key-${name}`)).toBeVisible();
    }),
    when("deactivating the key", { req: "AUTH-25" }, async () => {
      await page.getByTestId(`deactivate-${name}`).click();
      await expect(page.getByTestId(`key-${name}`)).toContainText(/inactive|false/i);
    }),
    then("deleting the key removes it from the list", { req: "AUTH-25" }, async () => {
      await page.getByTestId(`delete-${name}`).click();
      await expect(page.getByTestId(`key-${name}`)).toHaveCount(0);
    }),
  ]);
});

test(testTitle("E2E-11"), async ({ page, steps }) => {
  await steps.play([
    given("the runtime config on the settings page", () => page.goto("/settings")),
    when("editing config call_timeout 60 → 90", { req: "MGMT-1" }, async () => {
      await page.getByTestId("config-call_timeout").fill("90");
      await page.getByTestId("config-save-call_timeout").click();
    }),
    then("the new value persists across a reload", { req: "ARC-20" }, async () => {
      await page.reload();
      await expect(page.getByTestId("config-call_timeout")).toHaveValue("90");
    }),
    then("resetting restores the default", { req: "MGMT-1" }, async () => {
      await page.getByTestId("config-reset-call_timeout").click();
      await expect(page.getByTestId("config-call_timeout")).toHaveValue("60");
    }),
  ]);
});
