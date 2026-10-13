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
