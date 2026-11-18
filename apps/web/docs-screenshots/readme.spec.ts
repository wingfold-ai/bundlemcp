import { expect, test } from "@playwright/test";
import { STORAGE, adminApi } from "../tests/flows";

// The two screenshots at the top of the repository README: the upstream servers
// the seed registers, and a bundle's tool curation. Names are stable: the README
// links them as docs/public/screenshots/readme/<name>.png.

test.use({ storageState: STORAGE });

const OUT = "../../docs/public/screenshots/readme";
const BUNDLE = "assistant";

interface Tool {
  tool_id: string;
  server_name: string;
  name: string;
}

test("readme screenshots", async ({ page }) => {
  const api = await adminApi();
  // a previous run that stopped half-way leaves the bundle behind
  await api.delete(`bundles/${BUNDLE}`);
  try {
    await page.setViewportSize({ width: 1440, height: 560 });
    await page.goto("/upstreams");
    await expect(page.getByTestId("row-echo")).toBeVisible();
    await expect(page.getByTestId("row-identity-demo")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${OUT}/upstream-servers.png` });

    // one bundle over two servers, with a tool renamed, one re-described and one hidden
    await api.put(`bundles/${BUNDLE}`, {
      data: { name: BUNDLE, description: "The tools my assistant may use" },
    });
    for (const upstream of ["echo", "identity-demo"]) {
      await api.put(`bundles/${BUNDLE}/upstreams/${upstream}`, { data: { enabled: true } });
    }
    const tools: Tool[] = await (await api.get(`bundles/${BUNDLE}/tools`)).json();
    const tool = (server: string, name: string): string =>
      tools.find((t) => t.server_name === server && t.name === name)!.tool_id;
    await api.put(`bundles/${BUNDLE}/tools/${tool("echo", "shout")}`, {
      data: { enabled: true, override_name: "loud" },
    });
    await api.put(`bundles/${BUNDLE}/tools/${tool("echo", "reverse")}`, {
      data: { enabled: true, override_description: "Spell the text backwards" },
    });
    await api.put(`bundles/${BUNDLE}/tools/${tool("echo", "countdown")}`, {
      data: { enabled: false },
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/bundles/${BUNDLE}`);
    const curation = page.getByTestId("card-curation");
    await expect(curation).toContainText("loud");
    await curation.scrollIntoViewIfNeeded();
    await page.waitForLoadState("networkidle");
    await curation.screenshot({ path: `${OUT}/tool-curation.png` });
  } finally {
    await api.delete(`bundles/${BUNDLE}`);
    await api.dispose();
  }
});
