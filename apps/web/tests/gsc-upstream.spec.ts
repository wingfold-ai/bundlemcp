import { test, expect, given, when, then } from "./gherkin";
import { STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// seo-gsc does its own Google OAuth (its /connect page) and introspects the
// gateway-forwarded bearer; the UI must surface the forwarding config and the
// server's health once discovery has probed it.
test(testTitle("E2E-12"), async ({ page, steps }) => {
  await steps.play([
    given("the seo-gsc server detail page", async () => {
      await page.goto("/upstreams/seo-gsc");
      await expect(page.getByTestId("input-url")).toHaveValue("http://seo-gsc:8000/mcp");
    }),
    then("the seeded forward_headers pass the caller's bearer through", { req: "FWD-4" }, async () => {
      await expect(page.getByTestId("fwd-key-0")).toHaveValue("authorization");
    }),
    then("forwarding the caller's bearer is flagged as passthrough", { req: "FWD-7" }, async () => {
      await expect(page.getByTestId("passthrough-warning")).toBeVisible();
    }),
  ]);
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
    then("the connect link targets its gateway connect route", { req: "UPO-1" }, async () => {
      const href = await page.getByTestId("upstream-connect").getAttribute("href");
      expect(href).toContain(`/oauth/upstream/${name}/connect`);
      await page.getByTestId("delete-server").click();
      await page.waitForURL(/\/upstreams$/);
    }),
  ]);
});
