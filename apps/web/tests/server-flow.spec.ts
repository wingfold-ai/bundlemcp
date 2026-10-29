import { test, expect, given, when, then } from "./gherkin";
import { adminApi, STORAGE, withUpstream } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// Full server lifecycle against the live echo-mcp container.
test(testTitle("E2E-03"), async ({ page, steps }) => {
  const name = "e2e-echo";
  page.on("dialog", (d) => d.accept());

  await steps.play([
    given("the admin on the servers page", () => page.goto("/upstreams")),
    when("checking the echo-mcp URL before registering it", { req: "UPS-11" }, async () => {
      await page.getByTestId("create-url").fill("http://echo-mcp:9000/mcp");
      await page.getByTestId("create-inspect").click();
      await expect(page.getByTestId("inspection-state")).toContainText("ready", {
        timeout: 20_000,
      });
    }),
    then("no credential is detected and pre-selected", { req: "UI-6" }, async () => {
      await expect(page.getByTestId("source-none")).toBeChecked();
    }),
    when(`registering it as "${name}"`, { req: "UPS-2" }, async () => {
      await page.getByTestId("create-name").fill(name);
      await page.getByTestId("create-submit").click();
      await page.waitForURL(new RegExp(`/upstreams/${name}$`));
    }),
    when("refreshing tools so discovery probes the live upstream", { req: "UPS-17" }, async () => {
      await page.getByTestId("refresh-tools").click();
    }),
    then("the discovered echo tools are listed", { req: "UPS-17" }, async () => {
      await expect(page.getByTestId("tools-table")).toContainText("echo", { timeout: 20_000 });
    }),
    then("deleting the server removes it from the list", { req: "UPS-2" }, async () => {
      await page.getByTestId("delete-server").click();
      await page.waitForURL(/\/upstreams$/);
      await expect(page.getByTestId(`row-${name}`)).toHaveCount(0);
    }),
  ]);
});

test(testTitle("E2E-04"), async ({ page, steps }) => {
  await steps.play([
    given("the admin on the servers page", () => page.goto("/upstreams")),
    when("submitting a server name containing '__'", { req: "UI-4" }, async () => {
      await page.getByTestId("create-url").fill("http://x/mcp");
      await page.getByTestId("create-manual").click();
      await page.getByTestId("create-name").fill("bad__name");
      await page.getByTestId("create-submit").click();
    }),
    then("client-side validation blocks it before any row is created", { req: "UI-4" }, async () => {
      await expect(page.getByTestId("error")).toContainText("__");
      await expect(page.getByTestId("row-bad__name")).toHaveCount(0);
    }),
  ]);
});

test(testTitle("E2E-31"), async ({ page, steps }) => {
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "PUT") writes.push(r.url());
  });

  await steps.play([
    given("the admin on the Bundles page, where bundle demo exists", () => page.goto("/bundles")),
    when("typing demo as the name of a new bundle and submitting", { req: "UI-4" }, async () => {
      await page.getByTestId("create-name").fill("demo");
      await expect(page.getByTestId("create-name-hint")).toContainText("taken");
      await page.getByTestId("create-submit").click();
    }),
    then("no create request was sent", { req: "UI-4" }, async () => {
      expect(writes.filter((u) => u.includes("/api/v1/bundles/"))).toEqual([]);
    }),
    when("creating an endpoint named api from the demo bundle", { req: "UI-4" }, async () => {
      await page.goto("/bundles/demo");
      await page.getByTestId("create-endpoint-name").fill("api");
      await expect(page.getByTestId("create-endpoint-name-hint")).toContainText("reserved");
      await page.getByTestId("create-endpoint-submit").click();
    }),
    then("the reserved name is refused before anything is sent", { req: "UI-4" }, async () => {
      expect(writes.filter((u) => u.includes("/api/v1/endpoints/"))).toEqual([]);
    }),
  ]);
});

test(testTitle("E2E-32"), async ({ page, steps }) => {
  await steps.play([
    given("the admin opens the echo upstream", () => page.goto("/upstreams/echo")),
    then("the page is titled Upstream server: echo", { req: "UI-7" }, async () => {
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Upstream server: echo");
    }),
    when("renaming it to a name with a double underscore", { req: "UI-7" }, async () => {
      await page.getByTestId("rename-input").fill("bad__name");
    }),
    then("the message names an upstream, not a server", { req: "UI-7" }, async () => {
      await expect(page.getByTestId("rename-hint")).toHaveText('Upstream name must not contain "__"');
    }),
  ]);
});

test(testTitle("E2E-38"), async ({ page, steps }) => {
  const taken = "e2e-taken-name";
  const renames: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes(":rename")) renames.push(r.url());
  });

  await withUpstream({ name: taken, url: "http://echo-mcp:9000/mcp" }, async () => {
    await steps.play([
      given(`the admin on the echo upstream, while upstream ${taken} exists`, async () => {
        await page.goto("/upstreams/echo");
      }),
      when(`typing ${taken} as echo's new name and submitting`, { req: "UI-4" }, async () => {
        await page.getByTestId("rename-input").fill(taken);
        await page.getByTestId("rename-input").press("Enter");
      }),
      then("the name is reported as taken, and no rename is sent", { req: "UI-4" }, async () => {
        await expect(page.getByTestId("rename-hint")).toContainText("already taken");
        await expect(page.getByTestId("rename-submit")).toBeDisabled();
        expect(renames).toEqual([]);
      }),
    ]);
  });
});

// A dedicated upstream rather than the seeded echo: if the guard ever let the
// rename through, the seed every other scenario relies on would be renamed.
test(testTitle("E2E-42"), async ({ page, steps }) => {
  const upstream = "e2e-guarded";
  const bundle = "e2e-guard-bundle";
  const api = await adminApi();
  try {
    await withUpstream({ name: upstream, url: "http://echo-mcp:9000/mcp" }, async () => {
      await api.put(`bundles/${bundle}`, { data: { name: bundle, description: "e2e" } });
      await api.put(`bundles/${bundle}/upstreams/${upstream}`, { data: { enabled: true } });

      await steps.play([
        given(`upstream ${upstream} is a member of bundle ${bundle}`, { req: "UPS-5" }, async () => {
          await page.goto(`/upstreams/${upstream}`);
        }),
        when("renaming it without acknowledging the consequence", { req: "UPS-5" }, async () => {
          await page.getByTestId("rename-input").fill(`${upstream}-renamed`);
          await expect(page.getByTestId("rename-force")).not.toBeChecked();
          await page.getByTestId("rename-submit").click();
        }),
        then("the refusal shows on the danger zone card", { req: "UI-12" }, async () => {
          await expect(page.getByTestId("card-danger").getByTestId("error")).toBeVisible();
          await expect(page.getByTestId("card-danger").getByTestId("error")).not.toBeEmpty();
        }),
        then("the configuration card shows no error, and the upstream keeps its name", { req: "UI-12" }, async () => {
          await expect(page.getByTestId("card-config").getByTestId("error")).toHaveCount(0);
          await expect(page.getByRole("heading", { level: 1 })).toHaveText(
            `Upstream server: ${upstream}`,
          );
          expect((await api.get(`upstreams/${upstream}`)).ok()).toBeTruthy();
        }),
      ]);
    });
  } finally {
    await api.delete(`bundles/${bundle}`);
    await api.dispose();
  }
});
