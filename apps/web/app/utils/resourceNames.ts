// UI-4: client-side validation before submit. The rules are the gateway's
// (packages/bundlemcp/bundlemcp/models/base.py); the pattern is also published
// in the OpenAPI schema, the reserved list is not.
export const NAME_RE = /^[a-zA-Z0-9_-]+$/;
// BPR-2: a bundle prompt name additionally never contains "__".
export const PROMPT_NAME_RE = /^(?!.*__)[a-zA-Z0-9_-]+$/;
// BPR-6: a bundle resource name may be organised in "/" folders.
export const BUNDLE_RESOURCE_NAME_RE = /^[a-zA-Z0-9_-]+(\/[a-zA-Z0-9_.-]+)*$/;
export const RESERVED_ENDPOINT_NAMES = [
  "api",
  "oauth",
  ".well-known",
  "healthz",
  "readyz",
  "metrics",
  "docs",
  "login",
  "consent",
  "static",
];
