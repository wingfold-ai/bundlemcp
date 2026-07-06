import { test, expect } from "@playwright/test";

test.use({ storageState: "tests/.auth/admin.json" });

// Full server lifecycle against the live echo-mcp container (SRV-2/DISC-1).
test("create server, discover tools, delete (UI-1 servers)", async ({ page }) => {
  const name = "e2e-echo";
  await page.goto("/servers");

  await page.getByTestId("create-name").fill(name);
  await page.getByTestId("create-url").fill("http://echo-mcp:9000/mcp");
  await page.getByTestId("create-submit").click();
  await expect(page.getByTestId(`row-${name}`)).toBeVisible();

  await page.getByTestId(`open-${name}`).click();
  await page.getByTestId("refresh-tools").click();
  await expect(page.getByTestId("tools-table")).toContainText("echo", {
    timeout: 20_000,
  });

  page.on("dialog", (d) => d.accept());
  await page.getByTestId("delete-server").click();
  await page.waitForURL(/\/servers$/);
  await expect(page.getByTestId(`row-${name}`)).toHaveCount(0);
});

test("server name validation blocks '__' client-side (UI-4)", async ({ page }) => {
  await page.goto("/servers");
  await page.getByTestId("create-name").fill("bad__name");
  await page.getByTestId("create-url").fill("http://x/mcp");
  await page.getByTestId("create-submit").click();
  await expect(page.getByTestId("error")).toContainText("__");
  await expect(page.getByTestId("row-bad__name")).toHaveCount(0);
});
