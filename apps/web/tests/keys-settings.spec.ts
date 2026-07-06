import { test, expect } from "@playwright/test";

test.use({ storageState: "tests/.auth/admin.json" });

test("API key created with one-time value, then deactivated (KEY-1/KEY-4)", async ({
  page,
}) => {
  const name = "e2e-key";
  page.on("dialog", (d) => d.accept());
  await page.goto("/api-keys");

  await page.getByTestId("key-name").fill(name);
  await page.getByTestId("key-create").click();
  const value = await page.getByTestId("created-key-value").textContent();
  expect(value).toContain("bmcp_sk_");

  await expect(page.getByTestId(`key-${name}`)).toBeVisible();
  await page.getByTestId(`deactivate-${name}`).click();
  await expect(page.getByTestId(`key-${name}`)).toContainText(/inactive|false/i);

  await page.getByTestId(`delete-${name}`).click();
  await expect(page.getByTestId(`key-${name}`)).toHaveCount(0);
});

test("runtime config edit + reset (spec 02 Config)", async ({ page }) => {
  await page.goto("/settings");
  const input = page.getByTestId("config-call_timeout");
  await input.fill("90");
  await page.getByTestId("config-save-call_timeout").click();

  await page.reload();
  await expect(page.getByTestId("config-call_timeout")).toHaveValue("90");

  await page.getByTestId("config-reset-call_timeout").click();
  await expect(page.getByTestId("config-call_timeout")).toHaveValue("60");
});
