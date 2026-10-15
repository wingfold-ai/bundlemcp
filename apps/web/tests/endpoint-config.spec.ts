import { test, expect, given, when, then } from "./gherkin";
import { STORAGE, createApiKeyEndpoint, createEchoBundle, deleteEndpointAndBundle } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// Endpoint configuration must round-trip through the API and survive a reload:
// the two optional rate limits and the auth-mode set. Runs on a dedicated
// bundle/endpoint so the seeded ones stay untouched.
test(testTitle("E2E-08"), async ({ page, steps }) => {
  const bundle = "e2e-cfg-bundle";
  const endpoint = "e2e-cfg";
  page.on("dialog", (d) => d.accept());

  // Idempotent: clear anything a previously crashed run left behind.
  await deleteEndpointAndBundle(page, endpoint, bundle);

  await steps.play([
    given("an api_key endpoint over the echo bundle", async () => {
      await createEchoBundle(page, bundle);
      await createApiKeyEndpoint(page, endpoint, bundle);
      await page.goto(`/endpoints/${endpoint}`);
    }),
    when("setting an endpoint rate limit of 100 requests / 60s", { req: "EP-16" }, async () => {
      await page.getByTestId("rl-endpoint-limit").fill("100");
      await page.getByTestId("rl-endpoint-window").fill("60");
    }),
    when("adding the oauth auth mode alongside api_key, and saving", { req: "EP-3" }, async () => {
      await page.getByTestId("auth-mode-oauth").check();
      await page.getByTestId("save-endpoint").click();
    }),
    then("both settings persist across a reload", { req: "EP-16" }, async () => {
      await page.reload();
      await expect(page.getByTestId("rl-endpoint-limit")).toHaveValue("100");
      await expect(page.getByTestId("rl-endpoint-window")).toHaveValue("60");
      await expect(page.getByTestId("auth-mode-oauth")).toBeChecked();
      await expect(page.getByTestId("auth-mode-api_key")).toBeChecked();
    }),
  ]);

  await deleteEndpointAndBundle(page, endpoint, bundle);
});

// Allowed browser origins are edited one per line and stored normalised; the save is
// awaited before reloading so the reload cannot race it.
test(testTitle("E2E-22"), async ({ page, steps }) => {
  const bundle = "e2e-origins-bundle";
  const endpoint = "e2e-origins";
  page.on("dialog", (d) => d.accept());
  await deleteEndpointAndBundle(page, endpoint, bundle);

  await steps.play([
    given("an api_key endpoint, which allows every origin by default", { req: "EP-24" }, async () => {
      await createEchoBundle(page, bundle);
      await createApiKeyEndpoint(page, endpoint, bundle);
      await page.goto(`/endpoints/${endpoint}`);
      await expect(page.getByTestId("input-allowed-origins")).toHaveValue("*");
    }),
    when("listing two origins and saving", { req: "EP-24" }, async () => {
      await page.getByTestId("input-allowed-origins").fill("https://App.example/\nhttp://localhost:3000");
      const saved = page.waitForResponse(
        (r) => r.url().endsWith(`/api/v1/endpoints/${endpoint}`) && r.request().method() === "PUT",
      );
      await page.getByTestId("save-endpoint").click();
      expect((await saved).status()).toBe(200);
    }),
    then("they persist across a reload, normalised", { req: "EP-24" }, async () => {
      await page.reload();
      await expect(page.getByTestId("input-allowed-origins")).toHaveValue(
        "https://app.example\nhttp://localhost:3000",
      );
    }),
  ]);

  await deleteEndpointAndBundle(page, endpoint, bundle);
});
