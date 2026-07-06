import { test, expect } from "@playwright/test";

test.use({ storageState: "tests/.auth/admin.json" });

// seo-gsc does its own Google OAuth (its /connect page) and introspects the
// gateway-forwarded bearer (FWD-4); the UI must surface the forwarding config
// and the server's health once discovery has probed it.
test("seo-gsc server page shows forwarding + upstream status", async ({
  page,
}) => {
  await page.goto("/servers/seo-gsc");
  await expect(page.getByTestId("input-url")).toHaveValue(
    "http://seo-gsc:8000/mcp",
  );
  // the seeded forward_headers pass the bearer through
  await expect(page.getByTestId("fwd-key-0")).toHaveValue("authorization");
  // upstream oauth status card renders (shared/per-user status JSON)
  await expect(page.getByTestId("upstream-status")).toBeVisible();
});

// The gateway-native upstream OAuth flow (spec 23, UPO-1): the connect link
// must point at the gateway connect route. Following it requires a live
// upstream IdP, so only the wiring is asserted here.
test("upstream connect link targets the gateway connect route", async ({
  page,
}) => {
  await page.goto("/servers/seo-gsc");
  const href = await page
    .getByTestId("upstream-connect")
    .getAttribute("href");
  expect(href).toContain("/oauth/upstream/seo-gsc/connect");
});
