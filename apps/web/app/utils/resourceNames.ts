// Client-side naming rules, read from the published OpenAPI document rather than
// copied: `npm run openapi` regenerates openapi.json from the gateway's own
// constraints, and the next build applies whatever they now say.
import openapi from "~~/openapi.json";

/** The JSON Schema of a resource's `name` property, as far as naming rules go. */
interface NameSchema {
  pattern?: string;
  not?: { pattern?: string };
  "x-reserved-names"?: string[];
}

type Schemas = Record<string, { properties?: Record<string, NameSchema> }>;
const schemas = (openapi as unknown as { components: { schemas: Schemas } }).components.schemas;

/** The kinds of named resource a form creates or renames. */
export type NamedResource = "upstream" | "bundle" | "endpoint" | "prompt" | "resource";

const SCHEMA: Record<NamedResource, string> = {
  upstream: "ServerUpsert",
  bundle: "BundleUpsert",
  endpoint: "EndpointUpsert",
  prompt: "BundlePromptUpsert",
  resource: "BundleResourceUpsert",
};

const LABEL: Record<NamedResource, string> = {
  upstream: "Upstream name",
  bundle: "Bundle name",
  endpoint: "Endpoint name",
  prompt: "Prompt name",
  resource: "Resource name",
};

function nameSchema(kind: NamedResource): NameSchema {
  return schemas[SCHEMA[kind]]?.properties?.name ?? {};
}

/** A pattern with no regex syntax in it reads better as the text it forbids. */
function forbidden(pattern: string): string {
  return /^[\w-]+$/.test(pattern) ? `contain "${pattern}"` : `match ${pattern}`;
}

/**
 * Why `name` cannot be used for a resource of `kind`, or null when it can.
 *
 * `taken` are the names resources of that kind already have, so a duplicate is
 * reported before the request is sent; a concurrent create still shows the API's
 * own conflict.
 */
export function nameProblem(kind: NamedResource, name: string, taken: string[] = []): string | null {
  const label = LABEL[kind];
  if (!name) return `${label} is required`;
  const schema = nameSchema(kind);
  if (schema.pattern && !new RegExp(schema.pattern).test(name)) {
    return `${label} must match ${schema.pattern}`;
  }
  if (schema.not?.pattern && new RegExp(schema.not.pattern).test(name)) {
    return `${label} must not ${forbidden(schema.not.pattern)}`;
  }
  if (schema["x-reserved-names"]?.includes(name.toLowerCase())) {
    return `"${name}" is a reserved endpoint name`;
  }
  if (taken.includes(name)) return `${label} "${name}" is already taken`;
  return null;
}
