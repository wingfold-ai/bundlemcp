import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { useEditableField } from "~/composables/useEditableField";

interface Bundle {
  description: string;
  modes: string[];
}

function editing(initial: Bundle) {
  const bundle = ref<Bundle>(initial);
  const description = useEditableField(() => bundle.value.description);
  const modes = useEditableField(() => bundle.value.modes);
  return { bundle, description, modes };
}

describe("UI-14 useEditableField", () => {
  it("fills the field from the gateway's value", () => {
    const { description } = editing({ description: "e2e", modes: [] });
    expect(description.value).toBe("e2e");
  });

  it("keeps an unsaved edit when the data is read again", async () => {
    const { bundle, description } = editing({ description: "e2e", modes: [] });
    description.value = "e2e, edited";

    // the same bundle, read again: another card's action invalidated it
    bundle.value = { description: "e2e", modes: [] };
    await nextTick();
    bundle.value = { description: "changed elsewhere", modes: [] };
    await nextTick();

    expect(description.value).toBe("e2e, edited");
  });

  it("takes the gateway's value while untouched", async () => {
    const { bundle, description, modes } = editing({ description: "e2e", modes: ["none"] });
    modes.value = ["api_key"];

    bundle.value = { description: "changed elsewhere", modes: ["none"] };
    await nextTick();

    expect(description.value).toBe("changed elsewhere");
    expect(modes.value).toEqual(["api_key"]);
  });

  it("follows the gateway again once a save comes back", async () => {
    const { bundle, description } = editing({ description: "e2e", modes: [] });
    description.value = "saved";

    bundle.value = { description: "saved", modes: [] };
    await nextTick();
    bundle.value = { description: "changed again elsewhere", modes: [] };
    await nextTick();

    expect(description.value).toBe("changed again elsewhere");
  });

  it("compares lists by content, so a list edited in place counts as an edit", async () => {
    const { bundle, modes } = editing({ description: "e2e", modes: ["none"] });
    modes.value.push("api_key");

    bundle.value = { description: "e2e", modes: ["oauth"] };
    await nextTick();

    expect(modes.value).toEqual(["none", "api_key"]);
  });
});

describe("UI-14 useEditableField leaves the gateway's data alone", () => {
  it("edits a copy, so the cached read keeps the gateway's value", () => {
    const { bundle, modes } = editing({ description: "e2e", modes: ["none"] });
    modes.value.push("api_key");
    expect(bundle.value.modes).toEqual(["none"]);
  });
});
