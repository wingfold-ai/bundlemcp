import { test, expect, given, when, then, and } from "./gherkin";
import {
  STORAGE,
  createApiKey,
  createApiKeyEndpoint,
  createEchoBundle,
  deleteApiKey,
  deleteEndpointAndBundle,
  openMcp,
} from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// Cross-layer end-to-end: config authored entirely through the UI (bundle ->
// endpoint -> api key) must produce a working MCP endpoint whose calls relay to
// the upstream and land in the audit log. This is the one test that proves the
// UI, gateway relay, and audit trail line up on real config.
test(testTitle("E2E-07"), async ({ page, request, steps }) => {
  const bundle = "e2e-relay-bundle";
  const endpoint = "e2e-relay";
  const keyName = "e2e-relay-key";
  page.on("dialog", (d) => d.accept());

  // Idempotent: clear anything a previously crashed run left behind.
  await deleteApiKey(page, keyName);
  await deleteEndpointAndBundle(page, endpoint, bundle);

  let key = "";
  await steps.play([
    given("a bundle composed over the echo server", { req: "BND-6" }, async () => {
      await page.goto("/bundles");
      await createEchoBundle(page, bundle);
    }),
    and(`the bundle exposed as endpoint "${endpoint}"`, { req: "EP-7" }, async () => {
      await createApiKeyEndpoint(page, endpoint, bundle);
    }),
    and("an API key whose value is shown exactly once", { req: "KEY-1" }, async () => {
      await page.goto("/api-keys");
      key = await createApiKey(page, keyName);
    }),
    when(`calling POST /${endpoint}/mcp as an external MCP client`, { req: "EP-1" }, async () => {
      const mcp = await openMcp(request, endpoint, key);
      expect(await mcp.listTools()).toContain("echo__echo");
      // EP-3: api_key auth accepts the bearer and the call relays to upstream.
      expect(await mcp.callTool("echo__echo", { text: "relay-e2e" })).toContain("relay-e2e");
    }),
    then("the tool call appears in the audit log", { req: "AUD-1" }, async () => {
      // The audit write can lag the response, so re-apply the filter until the
      // row appears (no fixed sleeps).
      await page.goto("/audit");
      await page.getByTestId("filter-endpoint").fill(endpoint);
      await expect(async () => {
        await page.getByTestId("filter-apply").click();
        await expect(page.getByTestId("audit-table")).toContainText("echo__echo");
      }).toPass({ timeout: 15_000 });
      await expect(page.getByTestId("audit-table")).toContainText(endpoint);
    }),
  ]);

  await deleteApiKey(page, keyName);
  await deleteEndpointAndBundle(page, endpoint, bundle);
});
