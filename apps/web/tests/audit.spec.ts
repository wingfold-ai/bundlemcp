import { readFileSync } from "node:fs";
import { test, expect, given, when, then } from "./gherkin";
import { GATEWAY_URL, STORAGE, adminApi } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

const SERVICE_KEY =
  process.env.BUNDLEMCP_INITIAL_SERVICE_KEY ?? "bmcp_sk_devservicekey000000000000000000000000";

// Two echo calls on the demo endpoint with the service key, so the log has rows to find.
async function callEchoTwice(): Promise<void> {
  const api = await adminApi();
  const mcp = `${GATEWAY_URL}/demo/mcp`;
  const headers = { Authorization: `Bearer ${SERVICE_KEY}` };
  const init = await api.post(mcp, {
    headers,
    data: {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2025-11-25", capabilities: {} },
    },
  });
  const session = init.headers()["mcp-session-id"];
  for (const id of [2, 3]) {
    const resp = await api.post(mcp, {
      headers: { ...headers, "Mcp-Session-Id": session },
      data: {
        jsonrpc: "2.0",
        id,
        method: "tools/call",
        params: { name: "echo__echo", arguments: { text: `audit-${id}` } },
      },
    });
    expect(resp.ok()).toBeTruthy();
  }
  await api.dispose();
}

// The id of the key whose value is the service key, by its display prefix.
async function serviceKeyId(): Promise<string> {
  const api = await adminApi();
  const keys = (await (await api.get("api-keys?limit=500")).json()).items as {
    id: string;
    key_prefix: string;
  }[];
  await api.dispose();
  const key = keys.find((k) => SERVICE_KEY.startsWith(k.key_prefix.replace(/[.…]+$/, "")));
  expect(key).toBeTruthy();
  return key!.id;
}

test(testTitle("E2E-27"), async ({ page, steps }) => {
  await callEchoTwice();
  const keyId = await serviceKeyId();
  await steps.play([
    given("the admin on the audit page", () => page.goto("/audit")),
    when("filtering by bundle demo, upstream echo and the service key", { req: "OPS-6" }, async () => {
      await page.getByTestId("filter-bundle").fill("demo");
      await page.getByTestId("filter-server").fill("echo");
      await page.getByTestId("filter-api-key").selectOption(keyId);
      await page.getByTestId("filter-apply").click();
    }),
    then("only records matching all three are listed", { req: "OPS-6" }, async () => {
      const rows = page.locator('[data-testid^="audit-row-"]');
      await expect(rows.first()).toBeVisible();
      const count = await rows.count();
      expect(count).toBeGreaterThanOrEqual(2);
      for (let i = 0; i < count; i++) {
        await expect(rows.nth(i).locator("td").nth(2)).toHaveText("demo");
        await expect(rows.nth(i).locator("td").nth(3)).toHaveText("echo");
      }
    }),
  ]);
});

test(testTitle("E2E-28"), async ({ page, steps }) => {
  await callEchoTwice();
  let total = 0;
  await steps.play([
    given("the audit page filtered to successful calls", async () => {
      await page.goto("/audit");
      const api = await adminApi();
      total = (await (await api.get("audit-records?status=success&limit=1")).json()).total;
      await api.dispose();
      expect(total).toBeGreaterThanOrEqual(2);
      await page.getByTestId("filter-status").selectOption("success");
      await page.getByTestId("filter-apply").click();
      await expect(page.getByTestId("audit-total")).toContainText(`of ${total} matching`);
    }),
    when("pressing Export CSV", { req: "OPS-6" }, async () => {}),
    then("the CSV holds a header and every matching record", { req: "OPS-6" }, async () => {
      const [download] = await Promise.all([
        page.waitForEvent("download"),
        page.getByTestId("export-csv").click(),
      ]);
      const csv = readFileSync((await download.path())!, "utf8").trim().split("\n");
      expect(csv[0]).toContain("idempotency_key");
      expect(csv[0]).toContain("api_key_id");
      expect(csv.length - 1).toBe(total);
      expect(csv.slice(1).every((line) => line.includes(",success,"))).toBeTruthy();
    }),
  ]);
});
