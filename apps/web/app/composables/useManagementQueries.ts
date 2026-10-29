import type { components } from "~~/types/api";

type BundleRead = components["schemas"]["BundleRead"];
type ServerRead = components["schemas"]["ServerRead"];
type EndpointRead = components["schemas"]["EndpointRead"];
type BundleMemberRead = components["schemas"]["BundleMemberRead"];
type ApiKeyRead = components["schemas"]["ApiKeyRead"];
type EndpointProfileRead = components["schemas"]["EndpointProfileRead"];

// The management lists every page reads, each under one key so a page that
// shows the same list shares its cache entry and its invalidation.
const PAGE = { offset: 0, limit: 100 };

export function useUpstreams() {
  const api = useApi();
  return useQuery<ServerRead[]>(
    queryKeys.upstreams,
    async () => unwrap(await api.GET("/api/v1/upstreams", { params: { query: PAGE } })).items,
    { default: () => [] },
  );
}

export function useBundles() {
  const api = useApi();
  return useQuery<BundleRead[]>(
    queryKeys.bundles,
    async () => unwrap(await api.GET("/api/v1/bundles", { params: { query: PAGE } })).items,
    { default: () => [] },
  );
}

export function useEndpoints() {
  const api = useApi();
  return useQuery<EndpointRead[]>(
    queryKeys.endpoints,
    async () => unwrap(await api.GET("/api/v1/endpoints", { params: { query: PAGE } })).items,
    { default: () => [] },
  );
}

/** The endpoint profiles a form offers, with what each changes and any caveat. */
export function useProfiles() {
  const api = useApi();
  return useQuery<EndpointProfileRead[]>(
    queryKeys.profiles,
    async () => unwrap(await api.GET("/api/v1/endpoints/profiles")),
    { default: () => [] },
  );
}

/** Every bundle's members, by bundle name and then server name: the composition grid. */
export function useComposition() {
  const api = useApi();
  return useQuery<Record<string, Record<string, BundleMemberRead>>>(
    queryKeys.composition,
    async () => {
      const bundles = unwrap(
        await api.GET("/api/v1/bundles", { params: { query: PAGE } }),
      ).items;
      // membership is per bundle; fetch them together rather than one after another
      const memberships = await Promise.all(
        bundles.map(async (b) => {
          const members = unwrap(
            await api.GET("/api/v1/bundles/{name}/upstreams", {
              params: { path: { name: b.name } },
            }),
          );
          return [b.name, Object.fromEntries(members.map((m) => [m.server_name, m]))] as const;
        }),
      );
      return Object.fromEntries(memberships);
    },
    { default: () => ({}) },
  );
}

/** Every API key; the most the API pages at once, since the audit filter lists them all. */
export function useApiKeys() {
  const api = useApi();
  return useQuery<ApiKeyRead[]>(
    queryKeys.apiKeys,
    async () =>
      unwrap(await api.GET("/api/v1/api-keys", { params: { query: { offset: 0, limit: 500 } } }))
        .items,
    { default: () => [] },
  );
}
