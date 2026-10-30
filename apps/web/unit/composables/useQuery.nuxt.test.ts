import { afterEach, describe, expect, it } from "vitest";
import { effectScope, type EffectScope } from "vue";
import { invalidate, useQuery } from "~/composables/useQuery";

/** A fetcher that counts its calls, so a test can tell a cache hit from a fetch. */
function counted<T>(value: T) {
  const fetcher = async () => {
    fetcher.calls += 1;
    return value;
  };
  fetcher.calls = 0;
  return fetcher;
}

// Each read runs in its own effect scope, as it would in a page; stopping the
// scope is leaving the page, after which Nuxt forgets the read but the
// session cache keeps its result.
const open: EffectScope[] = [];

async function visit<T>(key: string, fetcher: () => Promise<T[]>) {
  const scope = effectScope();
  open.push(scope);
  return await scope.run(() => useQuery<T[]>(key, fetcher, { default: () => [] }))!;
}

function leave() {
  for (const scope of open.splice(0)) scope.stop();
}

describe("UI-3 useQuery", () => {
  afterEach(async () => {
    leave();
    // every key these tests read is one of these resources
    await invalidate("bundles", "endpoints");
  });

  it("renders a revisited query from the session cache instead of fetching it", async () => {
    const fetcher = counted(["demo"]);
    expect((await visit("bundles", fetcher)).data.value).toEqual(["demo"]);
    leave();

    expect((await visit("bundles", fetcher)).data.value).toEqual(["demo"]);
    expect(fetcher.calls).toBe(1);
  });

  it("invalidates a resource and its parameterised keys, and nothing else", async () => {
    const bundles = counted(["demo"]);
    const bundleTools = counted(["echo"]);
    const endpoints = counted(["api"]);
    await visit("bundles", bundles);
    await visit("bundles:x:tools", bundleTools);
    await visit("endpoints", endpoints);
    leave();

    await invalidate("bundles");
    await visit("bundles", bundles);
    await visit("bundles:x:tools", bundleTools);
    await visit("endpoints", endpoints);

    expect(bundles.calls).toBe(2);
    expect(bundleTools.calls).toBe(2);
    expect(endpoints.calls).toBe(1);
  });

  it("goes to the gateway on a manual refresh, even with a cached result", async () => {
    const fetcher = counted(["demo"]);
    await visit("bundles", fetcher);
    leave();

    const revisit = await visit("bundles", fetcher);
    expect(fetcher.calls).toBe(1);
    await revisit.refresh();
    expect(fetcher.calls).toBe(2);
  });
});
