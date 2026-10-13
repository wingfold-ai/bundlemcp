import { test, expect, given, when, then } from "./gherkin";
import { STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// Full server lifecycle against the live echo-mcp container.
test(testTitle("E2E-03"), async ({ page, steps }) => {
  const name = "e2e-echo";
  page.on("dialog", (d) => d.accept());

  await steps.play([
    given("the admin on the servers page", () => page.goto("/upstreams")),
    when("checking the echo-mcp URL before registering it", { req: "UPS-11" }, async () => {
      await page.getByTestId("create-url").fill("http://echo-mcp:9000/mcp");
      await page.getByTestId("create-inspect").click();
      await expect(page.getByTestId("inspection-state")).toContainText("ready", {
        timeout: 20_000,
      });
    }),
    then("no credential is detected and pre-selected", { req: "UI-6" }, async () => {
      await expect(page.getByTestId("source-none")).toBeChecked();
    }),
    when(`registering it as "${name}"`, { req: "UPS-2" }, async () => {
      await page.getByTestId("create-name").fill(name);
      await page.getByTestId("create-submit").click();
      await page.waitForURL(new RegExp(`/upstreams/${name}$`));
    }),
    when("refreshing tools so discovery probes the live upstream", { req: "UPS-17" }, async () => {
      await page.getByTestId("refresh-tools").click();
    }),
    then("the discovered echo tools are listed", { req: "UPS-17" }, async () => {
      await expect(page.getByTestId("tools-table")).toContainText("echo", { timeout: 20_000 });
    }),
    then("deleting the server removes it from the list", { req: "UPS-2" }, async () => {
      await page.getByTestId("delete-server").click();
      await page.waitForURL(/\/upstreams$/);
      await expect(page.getByTestId(`row-${name}`)).toHaveCount(0);
    }),
  ]);
});

test(testTitle("E2E-04"), async ({ page, steps }) => {
  await steps.play([
    given("the admin on the servers page", () => page.goto("/upstreams")),
    when("submitting a server name containing '__'", { req: "UI-4" }, async () => {
      await page.getByTestId("create-url").fill("http://x/mcp");
      await page.getByTestId("create-manual").click();
      await page.getByTestId("create-name").fill("bad__name");
      await page.getByTestId("create-submit").click();
    }),
    then("client-side validation blocks it before any row is created", { req: "UI-4" }, async () => {
      await expect(page.getByTestId("error")).toContainText("__");
      await expect(page.getByTestId("row-bad__name")).toHaveCount(0);
    }),
  ]);
});
