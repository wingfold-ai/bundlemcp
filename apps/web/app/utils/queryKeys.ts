/**
 * The cache keys of the management data, one place for every page and mutation.
 *
 * A key is `resource` or `resource:parameter…`; `invalidate(resource)` reaches
 * both, so a mutation names the resources it changes, not the pages that show them.
 */
export const queryKeys = {
  upstreams: "upstreams",
  upstream: (name: string) => `upstreams:${name}`,
  upstreamTools: (name: string) => `upstreams:${name}:tools`,
  upstreamOAuth: (name: string) => `upstreams:${name}:oauth`,
  bundles: "bundles",
  bundle: (name: string) => `bundles:${name}`,
  bundleMembers: (name: string) => `bundles:${name}:members`,
  bundleTools: (name: string) => `bundles:${name}:tools`,
  bundlePrompts: (name: string) => `bundles:${name}:prompts`,
  bundleResources: (name: string) => `bundles:${name}:resources`,
  composition: "composition",
  endpoints: "endpoints",
  endpoint: (name: string) => `endpoints:${name}`,
  profiles: "profiles",
  apiKeys: "api-keys",
  users: "users",
  /** The consents of the users whose rows are expanded, fetched together. */
  expandedConsents: (userIds: string[]) => `users:consents:${[...userIds].sort().join(",")}`,
  /** The consents of the signed-in person, shown on the catalogue. */
  myConsents: "users:me:consents",
  /** The audit records matching one applied filter set, serialised in a stable order. */
  audit: (filters: Record<string, string>) =>
    `audit:${new URLSearchParams(Object.entries(filters).sort()).toString()}`,
  config: "config",
  catalogue: "catalogue",
  catalogueBundle: (name: string) => `catalogue:${name}`,
} as const;
