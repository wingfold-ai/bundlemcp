import { test, expect, given, when, then, and } from "./gherkin";
import { adminApi, STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// The access-log line of a bundle write carries the route template, not the bundle's name,
// so the filter names the template and the throwaway bundle only makes the lines happen.
const BUNDLE_ROUTE = "/bundles/{name}";

// A buffer id is "<milliseconds>-<sequence>"; compare them as numbers, not as text.
function idOrder(a: string, b: string): number {
  const [am, as] = a.split("-").map(Number);
  const [bm, bs] = b.split("-").map(Number);
  return am !== bm ? am! - bm! : as! - bs!;
}

test(testTitle("E2E-36"), async ({ page, steps }) => {
  const bundle = `e2e-livelog-${Date.now()}`;
  const rows = page.getByTestId("log-row");
  const shownIds = async () =>
    (await rows.evaluateAll((els) => els.map((el) => el.getAttribute("data-log-id")))).filter(
      (id): id is string => Boolean(id),
    );
  let before: string[] = [];

  await steps.play([
    given("the admin on the live log page, filtered to bundle writes", { req: "OPS-15" }, async () => {
      await page.goto("/logs");
      await expect(page.getByTestId("logs-page")).toBeVisible();
      await page.getByTestId("logs-level").selectOption("info");
      // the text filter applies after a debounce, so "live" alone may still be the stream
      // from before it; wait for the filtered load, then for the stream that follows it
      const filtered = page.waitForResponse(
        (r) => r.url().includes("/api/v1/logs?") && r.url().includes("q=%2Fbundles"),
        { timeout: 15_000 },
      );
      await page.getByTestId("logs-text").fill(BUNDLE_ROUTE);
      await filtered;
      await expect(page.getByTestId("logs-state")).toHaveText("live", { timeout: 15_000 });
    }),
    when("pausing the stream", { req: "OPS-15" }, async () => {
      await page.getByTestId("logs-pause").click();
      await expect(page.getByTestId("logs-state")).toHaveText("paused");
      await expect(page.getByTestId("logs-pause")).toHaveText(/Resume/);
      before = await shownIds();
    }),
    and("a bundle is created and deleted while paused", async () => {
      const api = await adminApi();
      expect(
        (await api.put(`bundles/${bundle}`, { data: { name: bundle, description: "e2e" } })).ok(),
      ).toBeTruthy();
      expect((await api.delete(`bundles/${bundle}`)).ok()).toBeTruthy();
      await api.dispose();
      // nothing reaches a paused page
      expect(await shownIds()).toEqual(before);
    }),
    when("resuming", { req: "OPS-15" }, async () => {
      await page.getByTestId("logs-pause").click();
      await expect(page.getByTestId("logs-pause")).toHaveText(/Pause/);
      await expect(page.getByTestId("logs-state")).toHaveText("live", { timeout: 15_000 });
    }),
    then(
      "the writes logged during the pause are shown in order, without duplicates",
      { req: "OPS-15" },
      async () => {
        await expect
          .poll(async () => (await shownIds()).filter((id) => !before.includes(id)).length, {
            timeout: 15_000,
          })
          .toBeGreaterThanOrEqual(2);
        const ids = await shownIds();
        expect(new Set(ids).size).toBe(ids.length);
        expect([...ids].sort(idOrder)).toEqual(ids);
        const events = await page.getByTestId("log-event").allTextContents();
        expect(events.slice(before.length).every((e) => e.trim() === "http.request")).toBeTruthy();
      },
    ),
  ]);
});
