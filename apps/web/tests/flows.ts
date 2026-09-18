import { expect, type APIRequestContext, type Page } from "@playwright/test";

// Shared, marker-based flows for the UI e2e suite. Every selector here is a
// `data-testid` (never text or coordinates), so a visual/layout change does not
// break the tests and a marker rename is a one-file edit. Video-overlay concerns
// (the intro card and step captions) live in overlay.ts / gherkin.ts.

export const STORAGE = "tests/.auth/admin.json";
export const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8000";

// Compose a bundle over the seeded `echo` server through the UI.
export async function createEchoBundle(page: Page, bundle: string): Promise<void> {
  await page.goto("/bundles");
  await page.getByTestId("create-name").fill(bundle);
  await page.getByTestId("create-description").fill("e2e");
  await page.getByTestId("create-submit").click();
  await page.getByTestId(`open-${bundle}`).click();
  await page.getByTestId("member-select").selectOption("echo");
  await page.getByTestId("member-add").click();
  await expect(page.getByTestId("member-echo")).toBeVisible();
}

// Expose a bundle through a new api_key endpoint via the UI.
export async function createApiKeyEndpoint(
  page: Page,
  endpoint: string,
  bundle: string,
): Promise<void> {
  await page.goto(`/bundles/${bundle}`);
  await page.getByTestId("create-endpoint-name").fill(endpoint);
  await page.getByTestId("auth-mode-api_key").check();
  // The create form pre-selects "oauth"; clear it so the endpoint really is
  // api_key-only (otherwise later oauth assertions would be vacuous).
  await page.getByTestId("auth-mode-oauth").uncheck();
  await page.getByTestId("create-endpoint-submit").click();
  await expect(page.getByTestId(`bundle-endpoint-${endpoint}`)).toBeVisible();
}

// Create an API key through the UI and return its one-time secret value.
export async function createApiKey(page: Page, name: string): Promise<string> {
  await page.goto("/api-keys");
  await page.getByTestId("key-name").fill(name);
  await page.getByTestId("key-create").click();
  const value = (await page.getByTestId("created-key-value").textContent())?.trim() ?? "";
  expect(value).toContain("bmcp_sk_");
  return value;
}

// Best-effort teardown helpers (dialogs must already be auto-accepted by the
// caller). Guarded on presence so a half-completed test still cleans up.
export async function deleteApiKey(page: Page, name: string): Promise<void> {
  await page.goto("/api-keys");
  // Key names are not unique and the row marker is keyed by name, so a retried
  // run leaves several rows sharing one marker. Delete them one at a time until
  // none is left: matching a single row would fail strict mode and wedge the
  // teardown this helper exists to guarantee.
  const rows = page.getByTestId(`key-${name}`);
  for (let remaining = await rows.count(); remaining > 0; remaining--) {
    await page.getByTestId(`delete-${name}`).first().click();
    await expect(rows).toHaveCount(remaining - 1);
  }
}

// Idempotent teardown: probes the list page for the row before drilling in, so
// it is safe to call both before a test (to clear crashed-run leftovers) and
// after (normal cleanup) without ever acting on a name that no longer exists.
export async function deleteEndpointAndBundle(
  page: Page,
  endpoint: string,
  bundle: string,
): Promise<void> {
  // Each list is fetched after navigation, so the table must be on the page
  // before the row is counted: probing too early reads 0, silently skips the
  // delete, and leaves the fixture behind for the next run to trip over.
  await page.goto("/endpoints");
  await page.getByTestId("endpoints-table").waitFor();
  if ((await page.getByTestId(`open-${endpoint}`).count()) > 0) {
    await page.getByTestId(`open-${endpoint}`).click();
    await page.getByTestId("delete-endpoint").click();
    await page.waitForURL(/\/endpoints$/);
  }
  await page.goto("/bundles");
  await page.getByTestId("bundles-table").waitFor();
  if ((await page.getByTestId(`open-${bundle}`).count()) > 0) {
    await page.getByTestId(`open-${bundle}`).click();
    await page.getByTestId("delete-bundle").click();
    await page.waitForURL(/\/bundles$/);
  }
}

// Streamable-HTTP may frame a JSON-RPC reply as an SSE `data:` event; accept
// both so assertions do not depend on the transport's response encoding.
export function parseRpc(text: string): { result?: { tools?: { name: string }[] } } {
  const trimmed = text.trim();
  if (trimmed.startsWith("event:") || trimmed.startsWith("data:")) {
    const line = trimmed.split("\n").find((l) => l.startsWith("data:"));
    return JSON.parse((line ?? "data: {}").slice("data:".length).trim());
  }
  return JSON.parse(trimmed);
}

// A minimal external MCP client that speaks to the gateway over a given
// endpoint + bearer key — used to prove UI-authored config actually serves.
export async function openMcp(
  request: APIRequestContext,
  endpoint: string,
  key: string,
): Promise<{
  listTools: () => Promise<string[]>;
  callTool: (name: string, args: Record<string, unknown>) => Promise<string>;
}> {
  const url = `${GATEWAY_URL}/${endpoint}/mcp`;
  const headers = (sid?: string): Record<string, string> => ({
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
    ...(sid ? { "Mcp-Session-Id": sid } : {}),
  });

  const init = await request.post(url, {
    headers: headers(),
    data: {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "e2e", version: "0" },
      },
    },
  });
  expect(init.ok(), `initialize failed: HTTP ${init.status()}`).toBeTruthy();
  const sid = init.headers()["mcp-session-id"];
  expect(sid, "gateway returned an MCP session id").toBeTruthy();

  await request.post(url, {
    headers: headers(sid),
    data: { jsonrpc: "2.0", method: "notifications/initialized" },
  });

  return {
    async listTools(): Promise<string[]> {
      const r = await request.post(url, {
        headers: headers(sid),
        data: { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} },
      });
      const body = parseRpc(await r.text());
      return (body.result?.tools ?? []).map((t) => t.name);
    },
    async callTool(name: string, args: Record<string, unknown>): Promise<string> {
      const r = await request.post(url, {
        headers: headers(sid),
        data: {
          jsonrpc: "2.0",
          id: 3,
          method: "tools/call",
          params: { name, arguments: args },
        },
      });
      return await r.text();
    },
  };
}
