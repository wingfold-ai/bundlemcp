/** One argument the inspector's call form asks for, read from a tool's JSON Schema. */
export type FormField = {
  name: string;
  kind: "string" | "number" | "integer" | "boolean" | "enum";
  required: boolean;
  description?: string;
  options?: Array<string | number>;
};

type Schema = {
  type?: unknown;
  properties?: Record<string, Record<string, unknown>>;
  required?: unknown;
};

/**
 * The form fields for a tool's input schema, or null when the schema uses something a flat
 * form cannot express (nested objects, arrays, combinators): those tools are called with raw
 * JSON instead.
 */
export function formFields(schema: Record<string, unknown> | undefined): FormField[] | null {
  const s = (schema ?? {}) as Schema;
  if (s.type !== undefined && s.type !== "object") return null;
  const required = new Set(Array.isArray(s.required) ? (s.required as string[]) : []);
  const fields: FormField[] = [];
  for (const [name, prop] of Object.entries(s.properties ?? {})) {
    const description = typeof prop.description === "string" ? prop.description : undefined;
    const base = { name, required: required.has(name), description };
    if (Array.isArray(prop.enum) && prop.enum.every((v) => ["string", "number"].includes(typeof v))) {
      fields.push({ ...base, kind: "enum", options: prop.enum as Array<string | number> });
    } else if (["string", "number", "integer", "boolean"].includes(prop.type as string)) {
      fields.push({ ...base, kind: prop.type as FormField["kind"] });
    } else {
      return null;
    }
  }
  return fields;
}

/** The call's arguments from the form's values: empty optional fields are left out. */
export function formArguments(fields: FormField[], values: Record<string, unknown>): Record<string, unknown> {
  const args: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.name];
    if (field.kind === "boolean") {
      if (value !== undefined) args[field.name] = Boolean(value);
      continue;
    }
    if (value === undefined || value === "") continue;
    if (field.kind === "number" || field.kind === "integer") {
      args[field.name] = Number(value);
    } else if (field.kind === "enum") {
      const option = field.options?.find((o) => String(o) === String(value));
      args[field.name] = option ?? value;
    } else {
      args[field.name] = value;
    }
  }
  return args;
}

/** The form's values for some arguments, as the inputs hold them. */
export function formValues(fields: FormField[], args: Record<string, unknown>): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const field of fields) {
    const value = args[field.name];
    if (value === undefined) continue;
    values[field.name] = field.kind === "boolean" ? Boolean(value) : String(value);
  }
  return values;
}
