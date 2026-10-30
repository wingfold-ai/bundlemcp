import { describe, expect, it } from "vitest";
import { promptPlaceholders, renderPromptText } from "~/utils/renderPromptText";

describe("BND-20 renderPromptText", () => {
  it("replaces every placeholder with its sample value", () => {
    expect(renderPromptText("Hello {{name}}, meet {{other}}", { name: "Ada", other: "Bob" })).toBe(
      "Hello Ada, meet Bob",
    );
  });

  it("renders an argument without a value as the empty string", () => {
    expect(renderPromptText("Hello {{name}}!", {})).toBe("Hello !");
  });

  it("does not scan a substituted value again", () => {
    expect(renderPromptText("{{a}}", { a: "{{b}}", b: "no" })).toBe("{{b}}");
  });

  it("lists the placeholders a text refers to, in order", () => {
    expect(promptPlaceholders("{{a}} and {{b-c}} and {{a}}")).toEqual(["a", "b-c", "a"]);
    expect(promptPlaceholders("no placeholders")).toEqual([]);
  });
});
