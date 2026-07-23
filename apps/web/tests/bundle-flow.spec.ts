import { test, expect } from "@playwright/test";

test.use({ storageState: "tests/.auth/admin.json" });

// Bundle composition + curation (BND-4/6, TM-1/3) on a dedicated bundle so the
// seeded ones stay untouched.
test("compose bundle, curate tool, expose endpoint", async ({ page }) => {
  const bundle = "e2e-bundle";
  const endpoint = "e2e-endpoint";
  page.on("dialog", (d) => d.accept());

  await page.goto("/bundles");
  await page.getByTestId("create-name").fill(bundle);
  await page.getByTestId("create-description").fill("e2e test bundle");
  await page.getByTestId("create-submit").click();
  await page.getByTestId(`open-${bundle}`).click();

  // add echo as member
  await page.getByTestId("member-select").selectOption("echo");
  await page.getByTestId("member-add").click();
  await expect(page.getByTestId("member-echo")).toBeVisible();

  // curation row appears with prefixed presented name
  const row = page.getByTestId("curation-echo__echo");
  await expect(row).toBeVisible();
  await expect(row).toContainText("echo__echo");

  // override the presented name (TM-3)
  const toolId = await row.getAttribute("data-tool-id");
  await page.getByTestId(`override-name-${toolId}`).fill("just_echo");
  await page.getByTestId(`curation-save-${toolId}`).click();
  await expect(row).toContainText("just_echo");

  // expose via an endpoint and check the connection card (EP-7)
  await page.goto("/endpoints");
  await page.getByTestId("create-endpoint-name").fill(endpoint);
  await page.getByTestId("create-endpoint-bundle").selectOption(bundle);
  await page.getByTestId("auth-mode-api_key").check();
  await page.getByTestId("create-endpoint-submit").click();
  await page.getByTestId(`open-${endpoint}`).click();
  await expect(page.getByTestId("connection-url")).toContainText(
    `/${endpoint}/mcp`,
  );

  // cleanup: delete endpoint then bundle
  await page.getByTestId("delete-endpoint").click();
  await page.waitForURL(/\/endpoints$/);
  await page.goto(`/bundles/${bundle}`);
  await page.getByTestId("delete-bundle").click();
  await page.waitForURL(/\/bundles$/);
});

test("chatgpt profile shows the re-annotation warning (PROF-3)", async ({
  page,
}) => {
  await page.goto("/endpoints");
  await page
    .getByTestId("create-endpoint-profile")
    .selectOption("chatgpt");
  await expect(page.getByTestId("chatgpt-warning")).toBeVisible();
});
