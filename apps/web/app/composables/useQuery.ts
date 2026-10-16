import type { AsyncData } from "#app";

/**
 * The session's query cache: the last result of every query, by key.
 *
 * Nuxt drops a query's data once no page uses it, so a page revisited within the
 * session would start empty; this keeps the result until a mutation invalidates it.
 */
const cache = new Map<string, unknown>();

/**
 * Read data through the cache. The first visit fetches; a revisit renders the
 * cached result at once and refetches it in the background. `key` names the
 * resource and its parameters — see `queryKeys` — so `invalidate` can find it.
 */
export function useQuery<T>(
  key: MaybeRefOrGetter<string>,
  fetcher: () => Promise<T>,
  options: { default: () => T },
): AsyncData<T, QueryError | undefined> {
  let fromCache = false;
  const result = useAsyncData<T>(
    key,
    async () => {
      const value = await fetcher();
      cache.set(toValue(key), value);
      return value;
    },
    {
      default: options.default,
      getCachedData(cacheKey, _nuxtApp, context) {
        // an explicit refresh or an invalidation always goes to the gateway
        if (context.cause === "refresh:manual" || context.cause === "refresh:hook") {
          return undefined;
        }
        if (!cache.has(cacheKey)) return undefined;
        fromCache = true;
        return cache.get(cacheKey) as T;
      },
    },
  ) as unknown as AsyncData<T, QueryError | undefined>;
  onMounted(() => {
    if (fromCache) void result.refresh();
  });
  return result;
}

/**
 * Mark every cached query of these resources stale after a mutation.
 *
 * A key belongs to a resource when it is the resource or starts with
 * `resource:`. Queries on screen refetch now; the others refetch when next shown.
 */
export async function invalidate(...resources: string[]): Promise<void> {
  const matches = (key: string) =>
    resources.some((resource) => key === resource || key.startsWith(`${resource}:`));
  const stale = [...cache.keys()].filter(matches);
  for (const key of stale) cache.delete(key);
  const active = Object.keys(useNuxtApp().payload.data).filter(matches);
  await refreshNuxtData([...new Set([...stale, ...active])]);
}
