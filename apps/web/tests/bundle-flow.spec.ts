import { test, expect, given, when, then } from "./gherkin";
import { withUpstream, STORAGE } from "./flows";
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
      await page.goto(`/bundles/${bundle}`);
      await page.getByTestId("create-endpoint-name").fill(endpoint);
      await page.getByTestId("auth-mode-api_key").check();
      await page.getByTestId("create-endpoint-submit").click();
      await page.getByTestId(`bundle-endpoint-${endpoint}`).click();
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
    given("the create-endpoint form on a bundle's page", () => page.goto("/bundles/demo")),
    when("selecting the chatgpt profile", { req: "PROF-3" }, () =>
      page.getByTestId("create-endpoint-profile").selectOption("chatgpt"),
    ),
    then("a re-annotation warning is shown", { req: "PROF-3" }, async () => {
      await expect(page.getByTestId("chatgpt-warning")).toBeVisible();
    }),
  ]);
});

// The composition grid reads what the seeded demo bundle contains; one extra
// upstream, in no bundle, gives it a non-member to show.
test(testTitle("E2E-15"), async ({ page, steps }) => {
  const outsider = { name: "e2e-outsider", url: "http://echo-mcp:9000/mcp" };
  await withUpstream(outsider, () =>
    steps.play([
      given("the admin on the composition grid", { req: "UI-1" }, async () => {
        await page.goto("/bundles/matrix");
        await expect(page.getByTestId("matrix-table")).toBeVisible();
      }),
      then("a bundle's member upstream is marked and a non-member is not", { req: "BND-4" }, async () => {
        await expect(page.getByTestId("matrix-demo-echo").locator("span[aria-label]")).toBeVisible();
        await expect(page.getByTestId(`matrix-demo-${outsider.name}`)).toHaveText("·");
      }),
      then("each row counts its upstreams and each column its bundles", { req: "BND-4" }, async () => {
        // The seeded demo bundle holds echo and oauth-demo; the per-upstream
        // total spans every bundle in the database, so it is only ever asserted
        // to be positive — other scenarios add and remove bundles over echo.
        await expect(page.getByTestId("matrix-count-demo")).toHaveText("2");
        await expect(page.getByTestId("matrix-total-echo")).toHaveText(/^[1-9]\d*$/);
      }),
    ]),
  );
});

// The catalogue entry an administrator writes, read back on the catalogue page.
// Admins may open the catalogue too, so one session covers both sides.
test(testTitle("E2E-16"), async ({ page, steps }) => {
  const bundle = "e2e-catalogue";
  const endpoint = "e2e-catalogue-ep";
  page.on("dialog", (d) => d.accept());

  await steps.play([
    given(`a bundle "${bundle}" serving the echo server over OAuth`, { req: "BND-6" }, async () => {
      await page.goto("/bundles");
      await page.getByTestId("create-name").fill(bundle);
      await page.getByTestId("create-submit").click();
      await page.getByTestId(`open-${bundle}`).click();
      await page.getByTestId("member-select").selectOption("echo");
      await page.getByTestId("member-add").click();
      await expect(page.getByTestId("member-echo")).toBeVisible();
      await page.getByTestId("create-endpoint-name").fill(endpoint);
      await page.getByTestId("auth-mode-oauth").check();
      await page.getByTestId("create-endpoint-submit").click();
      await expect(page.getByTestId(`bundle-endpoint-${endpoint}`)).toBeVisible();
    }),
    when("the administrator writes a catalogue overview", { req: "BND-11" }, async () => {
      await page.goto(`/bundles/${bundle}`);
      await page.getByTestId("input-overview").fill("First paragraph.\n\nSecond paragraph.");
      await page.getByTestId("save-bundle").click();
      await page.reload();
      await expect(page.getByTestId("input-overview")).toHaveValue(/First paragraph/);
    }),
    then("the catalogue page shows it as paragraphs", { req: "BND-11" }, async () => {
      await page.goto(`/catalogue/${bundle}`);
      const overview = page.getByTestId("catalogue-overview");
      await expect(overview).toContainText("First paragraph.");
      await expect(overview).toContainText("Second paragraph.");
    }),
    then("the tools the bundle serves are listed with their descriptions", { req: "BND-11" }, async () => {
      await expect(page.getByTestId("catalogue-tools")).toBeVisible();
      const echoTool = page.getByTestId("catalogue-tool-echo__echo");
      // BND-11: the reader gets the title and the description, not the wire name
      await expect(echoTool).toContainText("Echo");
      await expect(echoTool).toContainText("Return the text unchanged.");
      await expect(echoTool).not.toContainText("echo__echo");
    }),
  ]);

  // cleanup: delete endpoint then bundle
  await page.goto(`/endpoints/${endpoint}`);
  await page.getByTestId("delete-endpoint").click();
  await page.waitForURL(/\/endpoints$/);
  await page.goto(`/bundles/${bundle}`);
  await page.getByTestId("delete-bundle").click();
  await page.waitForURL(/\/bundles$/);
});
