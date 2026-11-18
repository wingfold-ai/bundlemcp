import { test, expect, given, when, then } from "./gherkin";
import { STORAGE, withUpstream } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// An upstream that verifies the caller itself (introspecting the forwarded
// bearer) is configured to pass the caller's Authorization header through; the
// UI must surface that forwarding and flag it. The upstream is registered for
// this scenario only, so it needs nothing beyond the demo seed.
test(testTitle("E2E-12"), async ({ page, steps }) => {
  const upstream = {
    name: "e2e-forwarding",
    url: "http://echo-mcp:9000/mcp",
    forward_headers: { authorization: "authorization" },
  };
  await withUpstream(upstream, () =>
    steps.play([
      given("an upstream that receives the caller's bearer", async () => {
        await page.goto(`/upstreams/${upstream.name}`);
        await expect(page.getByTestId("input-url")).toHaveValue(upstream.url);
      }),
      then("its forward_headers pass the caller's bearer through", { req: "AUTH-30" }, async () => {
        await expect(page.getByTestId("fwd-key-0")).toHaveValue("authorization");
      }),
      then("forwarding the caller's bearer is flagged as passthrough", { req: "AUTH-33" }, async () => {
        await expect(page.getByTestId("passthrough-warning")).toBeVisible();
      }),
    ]),
  );
});

// The gateway-native upstream OAuth flow: the connect link of an OAuth server
// must point at the gateway connect route. Following it requires a live
// upstream IdP, so only the wiring is asserted here.
test(testTitle("E2E-13"), async ({ page, steps }) => {
  const name = "e2e-oauth";
  page.on("dialog", (d) => d.accept());
  await steps.play([
    given("the admin on the servers page", () => page.goto("/upstreams")),
    when("registering a server whose users sign in with their own account", { req: "UI-6" }, async () => {
      await page.getByTestId("create-url").fill("http://oauth-e2e.invalid/mcp");
      await page.getByTestId("create-manual").click();
      await page.getByTestId("create-name").fill(name);
      await page.getByTestId("source-per_user").check();
      await page.getByTestId("create-submit").click();
      await page.waitForURL(new RegExp(`/upstreams/${name}$`));
    }),
    then("the connect link targets its gateway connect route", { req: "UPS-25" }, async () => {
      const href = await page.getByTestId("upstream-connect").getAttribute("href");
      expect(href).toContain(`/oauth/upstream/${name}/connect`);
      await page.getByTestId("delete-server").click();
      await page.waitForURL(/\/upstreams$/);
    }),
  ]);
});
