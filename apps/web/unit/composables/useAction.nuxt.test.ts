import { afterEach, describe, expect, it } from "vitest";
import { effectScope, type EffectScope } from "vue";
import { useAction, ValidationProblem } from "~/composables/useAction";
import { invalidate, useQuery } from "~/composables/useQuery";

const scopes: EffectScope[] = [];

/** Read `key` through the session cache, counting the fetches. */
async function cachedRead(key: string) {
  const fetcher = async () => {
    fetcher.calls += 1;
    return [key];
  };
  fetcher.calls = 0;
  const scope = effectScope();
  scopes.push(scope);
  await scope.run(() => useQuery<string[]>(key, fetcher, { default: () => [] }))!;
  return fetcher;
}

describe("UI-12 useAction", () => {
  afterEach(async () => {
    for (const scope of scopes.splice(0)) scope.stop();
    await invalidate("bundles", "endpoints");
  });

  it("shows a broken form rule as the card's error and sends nothing", async () => {
    let sent = 0;
    const save = useAction(async (value: string) => {
      if (!value) throw new ValidationProblem("Enter a value first");
      sent += 1;
    });

    expect(await save.run("")).toBe(false);
    expect(save.error.value).toBe("Enter a value first");
    expect(sent).toBe(0);
    expect(save.busy.value).toBe(false);
  });

  it("shows the API's refusal as the card's error", async () => {
    const save = useAction(async () => ({ error: { detail: "name already taken" } }));

    expect(await save.run()).toBe(false);
    expect(save.error.value).toBe("name already taken");
  });

  it("clears the error and marks the named resources stale on success", async () => {
    const bundles = await cachedRead("bundles");
    const endpoints = await cachedRead("endpoints");
    let fail = true;
    const save = useAction(async () => (fail ? { error: { detail: "refused" } } : {}), {
      invalidates: () => ["bundles"],
    });
    await save.run();
    expect(save.error.value).toBe("refused");

    fail = false;
    expect(await save.run()).toBe(true);
    expect(save.error.value).toBe("");
    // the read still on screen refetches at once; the other one is left alone
    expect(bundles.calls).toBe(2);
    expect(endpoints.calls).toBe(1);
  });

  it("clears the previous error when it runs again", async () => {
    let seen = "";
    const save = useAction(async () => {
      seen = save.error.value;
      throw new ValidationProblem("still wrong");
    });
    await save.run();
    expect(save.error.value).toBe("still wrong");

    await save.run();
    expect(seen).toBe("");
  });

  it("keeps each card's error to itself", async () => {
    const members = useAction(async () => ({ error: { detail: "conflict" } }));
    const meta = useAction(async () => ({}));
    await members.run();
    await meta.run();

    expect(members.error.value).toBe("conflict");
    expect(meta.error.value).toBe("");
  });
});
