import { test, expect, given, when, then } from "./gherkin";
import { adminApi, withUpstream, STORAGE } from "./flows";
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
    then("its tools appear as curation rows, prefixed server__tool", { req: "BND-12" }, async () => {
      const row = page.getByTestId("curation-echo__echo");
      await expect(row).toBeVisible();
      await expect(row).toContainText("echo__echo");
      toolId = await row.getAttribute("data-tool-id");
    }),
    when("overriding the presented name echo__echo → just_echo", { req: "BND-14" }, async () => {
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
    when("selecting the write_as_read profile", { req: "EP-12" }, () =>
      page.getByTestId("create-endpoint-profile").selectOption("write_as_read"),
    ),
    then("a re-annotation warning is shown", { req: "EP-12" }, async () => {
      await expect(page.getByTestId("profile-warning")).toBeVisible();
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
      // the reader gets the title and the description, not the wire name
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

// The bundle's own context needs no member: a bundle on its own serves it.
test(testTitle("E2E-18"), async ({ page, steps }) => {
  const bundle = "e2e-context";
  page.on("dialog", (d) => d.accept());

  await steps.play([
    given(`a new bundle "${bundle}" with no upstream servers`, { req: "BND-6" }, async () => {
      await page.goto("/bundles");
      await page.getByTestId("create-name").fill(bundle);
      await page.getByTestId("create-submit").click();
      await page.getByTestId(`open-${bundle}`).click();
    }),
    when("the administrator writes a Markdown resource in a folder", { req: "BND-23" }, async () => {
      await page.getByTestId("resource-new").click();
      await page.getByTestId("resource-name").fill("guides/style");
      await page.getByTestId("resource-title").fill("House style");
      await page.getByTestId("resource-content").fill("# House style\n\n- Use **blue**");
      await page.getByTestId("resource-preview-toggle").check();
      await expect(page.getByTestId("resource-preview").locator("strong")).toHaveText("blue");
      await page.getByTestId("resource-save").click();
      await expect(page.getByTestId("resource-guides/style")).toContainText("House style");
    }),
    when("writes a prompt that takes an argument and embeds the resource", { req: "BND-20" }, async () => {
      await page.getByTestId("prompt-new").click();
      await page.getByTestId("prompt-name").fill("plot");
      await page.getByTestId("prompt-add-argument").click();
      await page.getByTestId("prompt-argument-0").locator("input").first().fill("series");
      await page.getByTestId("prompt-message-text-0").fill("Plot {{series}}.");
      await page.getByTestId("prompt-add-resource").click();
      await expect(page.getByTestId("prompt-message-resource-1")).toHaveValue("guides/style");
    }),
    then("the preview renders it with sample arguments", { req: "BND-31" }, async () => {
      await page.getByTestId("prompt-sample-series").fill("revenue");
      await expect(page.getByTestId("prompt-rendered-0")).toHaveText("Plot revenue.");
    }),
    then("it is saved and listed", { req: "BND-31" }, async () => {
      await page.getByTestId("prompt-save").click();
      await expect(page.getByTestId("prompt-plot")).toContainText("series");
    }),
    then("the embedded resource cannot be deleted while the prompt uses it", { req: "BND-20" }, async () => {
      await page.getByTestId("resource-delete-guides/style").click();
      await expect(page.getByTestId("resources-error")).toContainText("plot");
    }),
  ]);

  // cleanup: the bundle takes its prompts and resources with it
  await page.getByTestId("delete-bundle").click();
  await page.waitForURL(/\/bundles$/);
});

// The query layer: a bundle created on one page reaches another page that was
// already visited, without anyone reloading it.
test(testTitle("E2E-30"), async ({ page, steps }) => {
  const bundle = "e2e-cached";
  page.on("dialog", (d) => d.accept());

  await steps.play([
    given("the admin has visited the composition grid", { req: "UI-3" }, async () => {
      await page.goto("/bundles/matrix");
      await expect(page.getByTestId("matrix-table")).toBeVisible();
    }),
    when(`creating bundle "${bundle}" on the Bundles page`, { req: "UI-3" }, async () => {
      await page.getByTestId("nav-bundles").click();
      await page.getByTestId("create-name").fill(bundle);
      await page.getByTestId("create-submit").click();
      await expect(page.getByTestId(`open-${bundle}`)).toBeVisible();
    }),
    then("the composition grid shows it on returning, with no reload", { req: "UI-3" }, async () => {
      await page.getByTestId("nav-matrix").click();
      await expect(page.getByTestId(`matrix-row-${bundle}`)).toBeVisible();
    }),
  ]);
  const api = await adminApi();
  await api.delete(`bundles/${bundle}`);
  await api.dispose();
});

// Renaming a bundle keeps everything attached to it, but automation naming the old
// bundle would create a new one, so the admin must acknowledge that first.
test(testTitle("E2E-33"), async ({ page, steps }) => {
  const bundle = "e2e-rename-from";
  const renamed = "e2e-rename-to";
  const endpoint = "e2e-rename-api";
  const api = await adminApi();
  try {
    await api.put(`bundles/${bundle}`, { data: { name: bundle, description: "e2e" } });
    await api.put(`endpoints/${endpoint}`, {
      data: { name: endpoint, bundle_name: bundle, auth_modes: ["api_key"] },
    });

    await steps.play([
      given(`bundle "${bundle}" with endpoint "${endpoint}"`, { req: "BND-10" }, async () => {
        await page.goto(`/bundles/${bundle}`);
        await expect(page.getByTestId(`bundle-endpoint-${endpoint}`)).toBeVisible();
      }),
      when("typing the name of an existing bundle", { req: "BND-10" }, async () => {
        await page.getByTestId("bundle-rename-input").fill("demo");
      }),
      then("the name is refused before anything is sent", { req: "BND-10" }, async () => {
        await expect(page.getByTestId("bundle-rename-hint")).toBeVisible();
        await expect(page.getByTestId("bundle-rename-submit")).toBeDisabled();
      }),
      when(`typing the free name "${renamed}"`, { req: "BND-10" }, async () => {
        await page.getByTestId("bundle-rename-input").fill(renamed);
      }),
      then("the warning about documents naming the old bundle is shown", { req: "BND-10" }, async () => {
        await expect(page.getByTestId("bundle-rename-hint")).toBeHidden();
        await expect(page.getByTestId("bundle-rename-warning")).toContainText("new, empty bundle");
        await expect(page.getByTestId("bundle-rename-submit")).toBeDisabled();
      }),
      when("acknowledging the warning and renaming", { req: "BND-10" }, async () => {
        await page.getByTestId("bundle-rename-ack").check();
        await page.getByTestId("bundle-rename-submit").click();
      }),
      then("the page moves to the new name and the endpoint stays with the bundle", { req: "BND-10" }, async () => {
        await page.waitForURL(new RegExp(`/bundles/${renamed}$`));
        await expect(page.getByRole("heading", { name: `Bundle: ${renamed}` })).toBeVisible();
        await expect(page.getByTestId(`bundle-endpoint-${endpoint}`)).toBeVisible();
        expect((await api.get(`bundles/${bundle}`)).status()).toBe(404);
      }),
    ]);
  } finally {
    await api.delete(`endpoints/${endpoint}`);
    await api.delete(`bundles/${renamed}`);
    await api.delete(`bundles/${bundle}`);
    await api.dispose();
  }
});
