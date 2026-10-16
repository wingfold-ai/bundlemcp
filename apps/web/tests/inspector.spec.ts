import { test, expect, given, when, then, and } from "./gherkin";
import { adminApi, STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

test(testTitle("E2E-37"), async ({ page, steps }) => {
  const api = await adminApi();
  const demo = await (await api.get("endpoints/demo")).json();
  const created = await api.post("api-keys", {
    data: { name: `e2e-inspector-${Date.now()}`, kind: "endpoint", endpoint_ids: [demo.id] },
  });
  expect(created.ok()).toBeTruthy();
  const endpointKey = (await created.json()).key as string;

  await steps.play([
    given("the admin on the inspector, connected to the echo upstream", { req: "UI-9" }, async () => {
      await page.goto("/inspector");
      await page.getByTestId("inspector-kind-upstream").check();
      await page.getByTestId("inspector-upstream").selectOption("echo");
      await page.getByTestId("inspector-connect").click();
      await expect(page.getByTestId("inspector-connection")).toContainText("echo");
      await expect(page.getByTestId("inspector-protocol")).not.toHaveText("—");
      await expect(page.getByTestId("inspector-capabilities")).toContainText("tools");
    }),
    when("opening a tool with a required string argument", { req: "UI-9" }, async () => {
      await page.getByTestId("inspector-tool-echo").click();
      await expect(page.getByTestId("inspector-arg-text")).toHaveAttribute("required", "");
      await page.getByTestId("inspector-arg-text").fill("hello inspector");
    }),
    then("raw JSON shows the same arguments", { req: "UI-9" }, async () => {
      await page.getByTestId("inspector-raw-toggle").click();
      await expect(page.getByTestId("inspector-raw")).toHaveValue(/"text": "hello inspector"/);
      await page.getByTestId("inspector-raw-toggle").click();
      await expect(page.getByTestId("inspector-arg-text")).toHaveValue("hello inspector");
    }),
    and("calling it shows the result and how long it took", { req: "UI-9" }, async () => {
      await page.getByTestId("inspector-call").click();
      await expect(page.getByTestId("inspector-result")).toContainText("hello inspector");
      await expect(page.getByTestId("inspector-outcome")).toHaveAttribute("data-error", "false");
      await expect(page.getByTestId("inspector-duration")).toHaveText(/\d+ ms/);
    }),
    when("calling a tool that reports progress", { req: "UI-9" }, async () => {
      await page.getByTestId("inspector-tool-countdown").click();
      await page.getByTestId("inspector-arg-steps").fill("3");
      await page.getByTestId("inspector-call").click();
    }),
    then("each progress notification shows before the result", { req: "UI-9" }, async () => {
      const items = page.getByTestId("inspector-progress-item");
      await expect(items.first()).toBeVisible();
      await expect(page.getByTestId("inspector-outcome")).toHaveCount(0);
      await expect(items).toHaveCount(3);
      await expect(page.getByTestId("inspector-result")).toContainText("liftoff");
    }),
    and("a destructive tool asks before it is called", { req: "UI-9" }, async () => {
      await page.getByTestId("inspector-tool-shout").click();
      await page.getByTestId("inspector-arg-text").fill("quiet");
      page.once("dialog", (dialog) => dialog.dismiss());
      await page.getByTestId("inspector-call").click();
      await expect(page.getByTestId("inspector-outcome")).toHaveCount(0);
    }),
    when("calling a tool through an endpoint without its credential", { req: "UI-8" }, async () => {
      await page.getByTestId("inspector-kind-endpoint").check();
      await page.getByTestId("inspector-endpoint").selectOption("demo");
      await page.getByTestId("inspector-connect").click();
    }),
    then("the endpoint's own authentication refuses it", { req: "UI-8" }, async () => {
      await expect(page.getByTestId("error")).toContainText(/credential_required|oauth_required/);
    }),
    when("connecting again with an API key for the endpoint", { req: "UI-8" }, async () => {
      await page.getByTestId("inspector-credential").fill(endpointKey);
      await page.getByTestId("inspector-connect").click();
    }),
    then("its tools are listed as its clients see them, prefixed", { req: "UI-8" }, async () => {
      await expect(page.getByTestId("inspector-tool-echo__echo")).toBeVisible();
      await expect(page.getByTestId("error")).toHaveCount(0);
    }),
  ]);
});
