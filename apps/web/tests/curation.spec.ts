import { test, expect, given, when, then } from "./gherkin";
import { adminApi, STORAGE } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

type Tool = {
  tool_id: string;
  name: string;
  override_title: string | null;
  override_description: string | null;
  override_annotations: Record<string, unknown> | null;
  stale: boolean;
};

// Each scenario builds its own bundle over the seeded echo server, so the seeded
// bundles stay untouched, and removes it again whatever happens.
test(testTitle("E2E-19"), async ({ page, steps }) => {
  const bundle = "e2e-curation";
  const api = await adminApi();
  let reverse = "";
  let echo = "";
  const tools = async (): Promise<Tool[]> =>
    (await api.get(`bundles/${bundle}/tools`)).json();
  try {
    await api.put(`bundles/${bundle}`, { data: { name: bundle, description: "e2e" } });
    await api.put(`bundles/${bundle}/upstreams/echo`, { data: { enabled: true } });
    const listed = await tools();
    reverse = listed.find((t) => t.name === "reverse")!.tool_id;
    echo = listed.find((t) => t.name === "echo")!.tool_id;

    await steps.play([
      given(
        "a tool whose description and annotations were overridden through the API",
        { req: "BND-17" },
        async () => {
          await api.put(`bundles/${bundle}/tools/${reverse}`, {
            data: {
              enabled: true,
              override_description: "Set by the API",
              override_annotations: { readOnlyHint: true },
            },
          });
          await page.goto(`/bundles/${bundle}`);
          await expect(page.getByTestId(`overridden-${reverse}`)).toBeVisible();
        },
      ),
      when("an admin changes only its override title in the UI and saves", { req: "BND-16" }, async () => {
        await page.getByTestId(`override-title-${reverse}`).fill("Reversed");
        // the field shows the typed title before the save lands, so wait for the save itself
        const saved = page.waitForResponse(
          (r) => r.url().endsWith(`/tools/${reverse}`) && r.request().method() === "PUT",
        );
        await page.getByTestId(`curation-save-${reverse}`).click();
        expect((await saved).ok()).toBeTruthy();
        await expect(page.getByTestId(`override-title-${reverse}`)).toHaveValue("Reversed");
      }),
      then("the overrides set through the API are unchanged", { req: "BND-16" }, async () => {
        const saved = (await tools()).find((t) => t.tool_id === reverse)!;
        expect(saved.override_title).toBe("Reversed");
        expect(saved.override_description).toBe("Set by the API");
        expect(saved.override_annotations).toEqual({ readOnlyHint: true });
      }),
      when(
        "an admin enters a description and annotation override on another row and saves",
        { req: "BND-16" },
        async () => {
          await page.getByTestId(`override-description-${echo}`).fill("Echoes, curated");
          await page.getByTestId(`override-annotations-${echo}`).fill('{"readOnlyHint": true}');
          await page.getByTestId(`curation-save-${echo}`).click();
          await expect(page.getByTestId(`overridden-${echo}`)).toBeVisible();
        },
      ),
      then("the API reports both overrides", { req: "BND-17" }, async () => {
        const saved = (await tools()).find((t) => t.tool_id === echo)!;
        expect(saved.override_description).toBe("Echoes, curated");
        expect(saved.override_annotations).toEqual({ readOnlyHint: true });
      }),
    ]);
  } finally {
    await api.delete(`bundles/${bundle}`);
    await api.dispose();
  }
});

// A stale tool needs an upstream that stops listing one. The gateway's own
// endpoint is such an upstream: the outer server reaches it on the gateway's
// loopback, and disabling a tool in the inner bundle removes it from the list.
test(testTitle("E2E-20"), async ({ page, steps }) => {
  const inner = "e2e-inner";
  const outer = "e2e-outer";
  const api = await adminApi();
  page.on("dialog", (d) => d.accept());
  try {
    await api.put(`bundles/${inner}`, { data: { name: inner, description: "e2e" } });
    await api.put(`bundles/${inner}/upstreams/echo`, { data: { enabled: true } });
    await api.put(`endpoints/${inner}`, {
      data: { name: inner, bundle_name: inner, auth_modes: ["none"], allow_unauthenticated: true },
    });
    // The gateway serves the inner bundle to itself as an upstream whose tool list the test
    // can change. It is reached under its compose service name: the same endpoint under the
    // public URL is refused as a bundle member, since a bundle may not include the gateway.
    await api.put(`upstreams/${outer}`, {
      data: { name: outer, url: `http://gateway:8000/${inner}/mcp` },
    });
    await api.put(`bundles/${outer}`, { data: { name: outer, description: "e2e" } });
    await api.put(`bundles/${outer}/upstreams/${outer}`, { data: { enabled: true } });
    await api.post(`upstreams/${outer}:refresh-tools`);

    await steps.play([
      given("an upstream that stops listing one of its tools", { req: "UPS-19" }, async () => {
        const innerTools: Tool[] = await (await api.get(`bundles/${inner}/tools`)).json();
        const shout = innerTools.find((t) => t.name === "shout")!.tool_id;
        await api.put(`bundles/${inner}/tools/${shout}`, { data: { enabled: false } });
        const refreshed = await api.post(`upstreams/${outer}:refresh-tools`);
        expect((await refreshed.json()).changed).toBe(1);
      }),
      then("the bundle page flags the tool as stale", { req: "BND-16" }, async () => {
        await page.goto(`/bundles/${outer}`);
        const row = page.getByTestId(`curation-${outer}__echo__shout`);
        await expect(row).toContainText("stale");
      }),
      when("an admin refreshes and prunes on the upstream page", { req: "UPS-19" }, async () => {
        await page.goto(`/upstreams/${outer}`);
        await expect(page.getByTestId("tool-stale-echo__shout")).toBeVisible();
        await page.getByTestId("refresh-and-prune").click();
        await expect(page.getByTestId("refresh-result")).toContainText("1 pruned");
      }),
      then("the stale tool is gone", { req: "UPS-19" }, async () => {
        await expect(page.getByTestId("tool-echo__shout")).toHaveCount(0);
        await expect(page.getByTestId("tool-echo__echo")).toBeVisible();
      }),
    ]);
  } finally {
    await api.delete(`bundles/${outer}`);
    await api.delete(`upstreams/${outer}`);
    await api.delete(`endpoints/${inner}`);
    await api.delete(`bundles/${inner}`);
    await api.dispose();
  }
});

test(testTitle("E2E-21"), async ({ page, steps }) => {
  const bundle = "e2e-order";
  const second = "e2e-second-echo";
  const api = await adminApi();
  try {
    await api.put(`upstreams/${second}`, {
      data: { name: second, url: "http://echo-mcp:9000/mcp" },
    });
    await api.put(`bundles/${bundle}`, { data: { name: bundle, description: "e2e" } });
    await api.put(`bundles/${bundle}/upstreams/${second}`, { data: { enabled: true } });
    await api.put(`bundles/${bundle}/upstreams/echo`, { data: { enabled: true } });

    await steps.play([
      given("a bundle whose members are listed in the order they were added", { req: "BND-1" }, async () => {
        await page.goto(`/bundles/${bundle}`);
        const rows = page.getByTestId("members-table").locator("tbody tr");
        await expect(rows.nth(0)).toHaveAttribute("data-testid", `member-${second}`);
      }),
      when("an admin moves the second member up", { req: "BND-1" }, async () => {
        await page.getByTestId("member-up-echo").click();
      }),
      then("it is listed first, and stays first after a reload", { req: "BND-1" }, async () => {
        const rows = page.getByTestId("members-table").locator("tbody tr");
        await expect(rows.nth(0)).toHaveAttribute("data-testid", "member-echo");
        await page.reload();
        await expect(rows.nth(0)).toHaveAttribute("data-testid", "member-echo");
        const members = await (await api.get(`bundles/${bundle}/upstreams`)).json();
        expect(members.map((m: { server_name: string }) => m.server_name)).toEqual([
          "echo",
          second,
        ]);
      }),
    ]);
  } finally {
    await api.delete(`bundles/${bundle}`);
    await api.delete(`upstreams/${second}`);
    await api.dispose();
  }
});

test(testTitle("E2E-39"), async ({ page, steps }) => {
  const bundle = "e2e-curation-error";
  const api = await adminApi();
  try {
    await api.put(`bundles/${bundle}`, { data: { name: bundle, description: "e2e" } });
    await api.put(`bundles/${bundle}/upstreams/echo`, { data: { enabled: true } });
    const listed: Tool[] = await (await api.get(`bundles/${bundle}/tools`)).json();
    const echo = listed.find((t) => t.name === "echo")!.tool_id;

    await steps.play([
      given("a bundle with a member tool", { req: "UI-12" }, async () => {
        await page.goto(`/bundles/${bundle}`);
      }),
      when("the admin saves an annotation override that is not a JSON object", { req: "UI-12" }, async () => {
        await page.getByTestId(`override-annotations-${echo}`).fill("[1, 2]");
        await page.getByTestId(`curation-save-${echo}`).click();
      }),
      then("the tool curation card shows the error, and nothing else does", { req: "UI-12" }, async () => {
        await expect(page.getByTestId("card-curation").getByTestId("error")).toContainText(
          "must be a JSON object",
        );
        await expect(page.getByTestId("error")).toHaveCount(1);
      }),
    ]);
  } finally {
    await api.delete(`bundles/${bundle}`);
    await api.dispose();
  }
});

test(testTitle("E2E-40"), async ({ page, steps }) => {
  const bundle = "e2e-card-errors";
  const api = await adminApi();
  try {
    await api.put(`bundles/${bundle}`, { data: { name: bundle, description: "e2e" } });
    await api.put(`bundles/${bundle}/upstreams/echo`, { data: { enabled: true } });
    // the gateway would accept the toggle; answering 409 stands in for a concurrent change
    await page.route(`**/api/v1/bundles/${bundle}/upstreams/echo`, (route) =>
      route.request().method() === "PUT"
        ? route.fulfill({ status: 409, json: { detail: "the member changed meanwhile" } })
        : route.continue(),
    );

    await steps.play([
      given("the members card of a bundle shows an error from a refused member change", { req: "UI-12" }, async () => {
        await page.goto(`/bundles/${bundle}`);
        await page.getByTestId("member-toggle-echo").click();
        await expect(page.getByTestId("card-members").getByTestId("error")).toHaveText(
          "the member changed meanwhile",
        );
      }),
      when("the admin saves the bundle's description successfully", { req: "UI-12" }, async () => {
        await page.getByTestId("input-description").fill("e2e, edited");
        await page.getByTestId("save-bundle").click();
      }),
      then(
        "the description saved is the one typed, though the refused toggle made the page read the bundle again",
        { req: "UI-14" },
        async () => {
          await expect
            .poll(async () => (await (await api.get(`bundles/${bundle}`)).json()).description)
            .toBe("e2e, edited");
        },
      ),
      then("the members card still shows its error, and the meta card shows none", { req: "UI-12" }, async () => {
        await expect(page.getByTestId("card-members").getByTestId("error")).toHaveText(
          "the member changed meanwhile",
        );
        await expect(page.getByTestId("card-meta").getByTestId("error")).toHaveCount(0);
      }),
    ]);
  } finally {
    await api.delete(`bundles/${bundle}`);
    await api.dispose();
  }
});

test(testTitle("E2E-41"), async ({ page, steps }) => {
  const bundle = "e2e-load-error";
  const api = await adminApi();
  try {
    await api.put(`bundles/${bundle}`, { data: { name: bundle, description: "e2e" } });
    await page.route(`**/api/v1/bundles/${bundle}/tools`, (route) =>
      route.fulfill({ status: 500, json: { detail: "the tools could not be read" } }),
    );

    await steps.play([
      given("the gateway fails to return a bundle's tools", { req: "UI-12" }),
      when("the admin opens the bundle's detail page", { req: "UI-12" }, async () => {
        await page.goto(`/bundles/${bundle}`);
      }),
      then("the load error shows at the top of the page, on no card", { req: "UI-12" }, async () => {
        await expect(page.getByTestId("error")).toHaveText("the tools could not be read");
        await expect(page.locator('[data-testid^="card-"] [data-testid="error"]')).toHaveCount(0);
      }),
    ]);
  } finally {
    await api.delete(`bundles/${bundle}`);
    await api.dispose();
  }
});
