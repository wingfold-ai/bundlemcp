import { describe, expect, it } from "vitest";
import { formArguments, formFields, formValues, type FormField } from "~/utils/schemaForm";

describe("UI-9 formFields", () => {
  it("turns a flat object schema into one field per property", () => {
    const fields = formFields({
      type: "object",
      required: ["text"],
      properties: {
        text: { type: "string", description: "What to echo" },
        times: { type: "integer" },
        loud: { type: "boolean" },
        tone: { enum: ["calm", "angry"] },
      },
    });
    expect(fields).toEqual([
      { name: "text", kind: "string", required: true, description: "What to echo" },
      { name: "times", kind: "integer", required: false, description: undefined },
      { name: "loud", kind: "boolean", required: false, description: undefined },
      {
        name: "tone",
        kind: "enum",
        required: false,
        description: undefined,
        options: ["calm", "angry"],
      },
    ]);
  });

  it("treats a missing schema as a tool without arguments", () => {
    expect(formFields(undefined)).toEqual([]);
  });

  it("gives up on a nested object, which needs raw JSON", () => {
    expect(
      formFields({ type: "object", properties: { where: { type: "object", properties: {} } } }),
    ).toBeNull();
  });

  it("gives up on a schema that is not an object", () => {
    expect(formFields({ type: "array" })).toBeNull();
  });
});

describe("UI-9 formArguments and formValues", () => {
  const fields: FormField[] = [
    { name: "text", kind: "string", required: true },
    { name: "times", kind: "integer", required: false },
    { name: "loud", kind: "boolean", required: false },
    { name: "level", kind: "enum", required: false, options: [1, 2] },
  ];

  it("converts the inputs' values to typed arguments and leaves out empty ones", () => {
    expect(formArguments(fields, { text: "hi", times: "3", loud: true, level: "2" })).toEqual({
      text: "hi",
      times: 3,
      loud: true,
      level: 2,
    });
    expect(formArguments(fields, { text: "hi", times: "" })).toEqual({ text: "hi" });
  });

  it("round-trips arguments through the form's values", () => {
    const args = { text: "hi", times: 3, loud: false, level: 1 };
    const values = formValues(fields, args);
    expect(values).toEqual({ text: "hi", times: "3", loud: false, level: "1" });
    expect(formArguments(fields, values)).toEqual(args);
  });
});
