import { test, expect, given, when, then } from "./gherkin";
import { adminApi, STORAGE } from "./flows";
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

test(testTitle("E2E-29"), async ({ page, steps }) => {
  const name = "e2e-scoped-key";
  page.on("dialog", (d) => d.accept());

  await steps.play([
    given("the admin on the API keys page", () => page.goto("/api-keys")),
    when(`creating endpoint key "${name}" scoped to the claude endpoint`, { req: "UI-1" }, async () => {
      await page.getByTestId("key-name").fill(name);
      await page.getByTestId("key-kind").selectOption("endpoint");
      await page.getByTestId("scope-claude").check();
      await page.getByTestId("key-create").click();
    }),
    then("the list shows the key's scope", { req: "UI-1" }, async () => {
      await expect(page.getByTestId(`scope-cell-${name}`)).toHaveText("claude");
    }),
    when("deactivating it, then re-activating it", { req: "AUTH-25" }, async () => {
      await page.getByTestId(`deactivate-${name}`).click();
      await expect(page.getByTestId(`key-${name}`)).toContainText(/inactive/i);
      await page.getByTestId(`activate-${name}`).click();
    }),
    then("the key is active again", { req: "UI-1" }, async () => {
      await expect(page.getByTestId(`key-${name}`)).not.toContainText(/inactive/i);
      await expect(page.getByTestId(`deactivate-${name}`)).toBeVisible();
      await page.getByTestId(`delete-${name}`).click();
      await expect(page.getByTestId(`key-${name}`)).toHaveCount(0);
    }),
  ]);
});

test(testTitle("E2E-34"), async ({ page, steps }) => {
  const bundle = "e2e-imported";
  const api = await adminApi();
  const document = { version: 1, bundles: [{ name: bundle, description: "from a file" }] };
  try {
    await steps.play([
      given("the admin on the settings page", () => page.goto("/settings")),
      when("clicking Export", { req: "MGMT-22" }, async () => {
        const download = page.waitForEvent("download");
        await page.getByTestId("export-config").click();
        expect((await download).suggestedFilename()).toBe("bundlemcp-export.json");
      }),
      when(`choosing a document that creates bundle "${bundle}"`, { req: "MGMT-22" }, async () => {
        await page.getByTestId("import-file").setInputFiles({
          name: "import.json",
          mimeType: "application/json",
          buffer: Buffer.from(JSON.stringify(document)),
        });
      }),
      then("the dry-run report shows it as created, and nothing is written yet", { req: "MGMT-19" }, async () => {
        await expect(page.getByTestId(`import-result-bundle-${bundle}`)).toContainText("created");
        expect((await api.get(`bundles/${bundle}`)).status()).toBe(404);
      }),
      then("confirming the import writes it", { req: "MGMT-22" }, async () => {
        await page.getByTestId("import-confirm").click();
        await expect(page.getByTestId("import-applied")).toBeVisible();
        expect((await api.get(`bundles/${bundle}`)).status()).toBe(200);
      }),
    ]);
  } finally {
    await api.delete(`bundles/${bundle}`);
    await api.dispose();
  }
});
