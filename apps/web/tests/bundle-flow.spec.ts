import { test, expect, given, when, then } from "./gherkin";
import { STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// Bundle composition + curation on a dedicated bundle so the seeded ones stay
// untouched.
test(testTitle("E2E-05"), async ({ page, steps }) => {
  const bundle = "e2e-bundle";
  const endpoint = "e2e-endpoint";
  page.on("dialog", (d) => d.accept());

  let toolId: string | null = null;

  await steps.play([
    given(`a new bundle "${bundle}"`, { req: "BND-6" }, async () => {
      await page.goto("/bundles");
      await page.getByTestId("create-name").fill(bundle);
      await page.getByTestId("create-description").fill("e2e test bundle");
      await page.getByTestId("create-submit").click();
      await page.getByTestId(`open-${bundle}`).click();
    }),
    when("adding the echo server as a bundle member", { req: "BND-4" }, async () => {
      await page.getByTestId("member-select").selectOption("echo");
      await page.getByTestId("member-add").click();
      await expect(page.getByTestId("member-echo")).toBeVisible();
    }),
    then("its tools appear as curation rows, prefixed server__tool", { req: "TM-1" }, async () => {
      const row = page.getByTestId("curation-echo__echo");
      await expect(row).toBeVisible();
      await expect(row).toContainText("echo__echo");
      toolId = await row.getAttribute("data-tool-id");
    }),
    when("overriding the presented name echo__echo → just_echo", { req: "TM-3" }, async () => {
      await page.getByTestId(`override-name-${toolId}`).fill("just_echo");
      await page.getByTestId(`curation-save-${toolId}`).click();
      await expect(page.getByTestId("curation-echo__echo")).toContainText("just_echo");
    }),
    when(`exposing the bundle as endpoint "${endpoint}"`, { req: "EP-7" }, async () => {
      await page.goto("/endpoints");
      await page.getByTestId("create-endpoint-name").fill(endpoint);
      await page.getByTestId("create-endpoint-bundle").selectOption(bundle);
      await page.getByTestId("auth-mode-api_key").check();
      await page.getByTestId("create-endpoint-submit").click();
      await page.getByTestId(`open-${endpoint}`).click();
    }),
    then("the connection card shows the copy-paste MCP URL", { req: "EP-7" }, async () => {
      await expect(page.getByTestId("connection-url")).toContainText(`/${endpoint}/mcp`);
    }),
  ]);

  // cleanup: delete endpoint then bundle
  await page.getByTestId("delete-endpoint").click();
  await page.waitForURL(/\/endpoints$/);
  await page.goto(`/bundles/${bundle}`);
  await page.getByTestId("delete-bundle").click();
  await page.waitForURL(/\/bundles$/);
});

test(testTitle("E2E-06"), async ({ page, steps }) => {
  await steps.play([
    given("the create-endpoint form on the endpoints page", () => page.goto("/endpoints")),
    when("selecting the chatgpt profile", { req: "PROF-3" }, () =>
      page.getByTestId("create-endpoint-profile").selectOption("chatgpt"),
    ),
    then("a re-annotation warning is shown", { req: "PROF-3" }, async () => {
      await expect(page.getByTestId("chatgpt-warning")).toBeVisible();
    }),
  ]);
});
