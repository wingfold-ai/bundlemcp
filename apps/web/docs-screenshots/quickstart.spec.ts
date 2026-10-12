import { expect, request as apiRequest, test, type Page } from "@playwright/test";
import { GATEWAY_URL, STORAGE } from "../tests/flows";

// The UI walk-through in docs/guide/quickstart.md, one screenshot per step.
// Names are stable: the page links them as /screenshots/quickstart/<name>.png.

test.use({ storageState: STORAGE });

const OUT = "../../docs/public/screenshots/quickstart";
const SERVER = "my-server";
const BUNDLE = "tools";
const ENDPOINT = "tools";
const SERVICE_KEY =
  process.env.BUNDLEMCP_INITIAL_SERVICE_KEY ?? "bmcp_sk_devservicekey000000000000000000000000";

async function shot(page: Page, name: string): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
}

// A previous run that stopped half-way leaves resources behind; remove them so
// the walk-through always starts from the seed alone. The request context is
// built with an empty storage state, since it would otherwise inherit the admin
// session cookie, and the gateway refuses a cookie-authenticated DELETE that
// carries no browser origin; the service key alone is accepted.
async function removeLeftovers(): Promise<void> {
  const api = await apiRequest.newContext({
    storageState: { cookies: [], origins: [] },
    extraHTTPHeaders: { Authorization: `Bearer ${SERVICE_KEY}` },
  });
  for (const path of [`endpoints/${ENDPOINT}`, `bundles/${BUNDLE}`, `servers/${SERVER}`]) {
    const response = await api.delete(`${GATEWAY_URL}/api/v1/${path}`);
    expect([204, 404], `DELETE ${path}: ${await response.text()}`).toContain(response.status());
  }
  await api.dispose();
}

test("quickstart walk-through", async ({ page }) => {
  page.on("dialog", (d) => d.accept());
  await removeLeftovers();

  await page.goto("/servers");
  await expect(page.getByTestId("row-echo")).toBeVisible();
  await shot(page, "01-upstream-servers");

  await page.getByTestId("create-url").fill("http://echo-mcp:9000/mcp");
  await page.getByTestId("create-inspect").click();
  await expect(page.getByTestId("inspection-state")).toContainText("ready", { timeout: 20_000 });
  await page.getByTestId("create-name").fill(SERVER);
  await shot(page, "02-register-upstream-server");

  await page.getByTestId("create-submit").click();
  await page.waitForURL(new RegExp(`/servers/${SERVER}$`));
  await page.getByTestId("refresh-tools").click();
  await expect(page.getByTestId("tools-table")).toContainText("echo", { timeout: 20_000 });
  await page.getByTestId("tools-table").scrollIntoViewIfNeeded();
  await shot(page, "03-discovered-tools");

  await page.goto("/bundles");
  await page.getByTestId("create-name").fill(BUNDLE);
  await page.getByTestId("create-description").fill("My tools and the echo tools");
  await page.getByTestId("create-submit").click();
  await page.getByTestId(`open-${BUNDLE}`).click();
  for (const member of [SERVER, "echo"]) {
    await page.getByTestId("member-select").selectOption(member);
    await page.getByTestId("member-add").click();
    await expect(page.getByTestId(`member-${member}`)).toBeVisible();
  }
  await page.getByTestId("members-table").scrollIntoViewIfNeeded();
  await shot(page, "04-bundle-members");

  await page.getByTestId("create-endpoint-name").fill(ENDPOINT);
  await page.getByTestId("auth-mode-api_key").check();
  await page.getByTestId("auth-mode-oauth").uncheck();
  await page.getByTestId("create-endpoint-name").scrollIntoViewIfNeeded();
  await shot(page, "05-create-endpoint");
  await page.getByTestId("create-endpoint-submit").click();
  await expect(page.getByTestId(`bundle-endpoint-${ENDPOINT}`)).toBeVisible();

  await page.goto(`/endpoints/${ENDPOINT}`);
  await expect(page.getByTestId("connection-url")).toContainText(`/${ENDPOINT}/mcp`);
  await shot(page, "06-endpoint-connection");

  await removeLeftovers();
});
