import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { useEditableRows } from "~/composables/useEditableRows";

interface Tool {
  id: string;
  title: string;
}

function curated(initial: Tool[]) {
  const tools = ref<Tool[]>(initial);
  const rows = useEditableRows(
    tools,
    (t) => t.id,
    (t) => ({ title: t.title }),
  );
  return { tools, rows };
}

describe("BND-16 useEditableRows", () => {
  it("fills one draft per item from the gateway's values", () => {
    const { rows } = curated([
      { id: "a", title: "A" },
      { id: "b", title: "B" },
    ]);
    expect(rows.value).toEqual({ a: { title: "A" }, b: { title: "B" } });
  });

  it("keeps an unsaved edit when the list is refetched", async () => {
    const { tools, rows } = curated([
      { id: "a", title: "A" },
      { id: "b", title: "B" },
    ]);
    rows.value.a!.title = "edited, not saved";

    tools.value = [
      { id: "a", title: "A" },
      { id: "b", title: "B, changed elsewhere" },
    ];
    await nextTick();

    expect(rows.value.a).toEqual({ title: "edited, not saved" });
    expect(rows.value.b).toEqual({ title: "B, changed elsewhere" });
  });

  it("replaces a saved row with the gateway's values", async () => {
    const { tools, rows } = curated([{ id: "a", title: "A" }]);
    rows.value.a!.title = "Saved";

    // the save came back: the gateway now reports the edit, so the row is no longer a draft
    tools.value = [{ id: "a", title: "Saved" }];
    await nextTick();
    tools.value = [{ id: "a", title: "Changed again elsewhere" }];
    await nextTick();

    expect(rows.value.a).toEqual({ title: "Changed again elsewhere" });
  });

  it("drops the draft of an item the gateway no longer lists", async () => {
    const { tools, rows } = curated([
      { id: "a", title: "A" },
      { id: "b", title: "B" },
    ]);
    tools.value = [{ id: "a", title: "A" }];
    await nextTick();
    expect(Object.keys(rows.value)).toEqual(["a"]);
  });
});
