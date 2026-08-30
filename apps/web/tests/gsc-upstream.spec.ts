import { test, expect, given, then } from "./gherkin";
import { STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// seo-gsc does its own Google OAuth (its /connect page) and introspects the
// gateway-forwarded bearer; the UI must surface the forwarding config and the
// server's health once discovery has probed it.
test(testTitle("E2E-12"), async ({ page, steps }) => {
  await steps.play([
    given("the seo-gsc server detail page", async () => {
      await page.goto("/servers/seo-gsc");
      await expect(page.getByTestId("input-url")).toHaveValue("http://seo-gsc:8000/mcp");
    }),
    then("the seeded forward_headers pass the caller's bearer through", { req: "FWD-4" }, async () => {
      await expect(page.getByTestId("fwd-key-0")).toHaveValue("authorization");
    }),
    then("the upstream OAuth status card renders", { req: "FWD-4" }, async () => {
      await expect(page.getByTestId("upstream-status")).toBeVisible();
    }),
  ]);
});

// The gateway-native upstream OAuth flow: the connect link must point at the
// gateway connect route. Following it requires a live upstream IdP, so only the
// wiring is asserted here.
test(testTitle("E2E-13"), async ({ page, steps }) => {
  await steps.play([
    given("the seo-gsc server detail page", () => page.goto("/servers/seo-gsc")),
    then("the connect link targets /oauth/upstream/seo-gsc/connect", { req: "UPO-1" }, async () => {
      const href = await page.getByTestId("upstream-connect").getAttribute("href");
      expect(href).toContain("/oauth/upstream/seo-gsc/connect");
    }),
  ]);
});
