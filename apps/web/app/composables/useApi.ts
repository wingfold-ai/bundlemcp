import createClient from "openapi-fetch";
import type { paths } from "~~/types/api";

let client: ReturnType<typeof createClient<paths>> | null = null;

/** Typed client for the management API (UI-3: generated types, cookie auth). */
export function useApi() {
  if (!client) {
    const config = useRuntimeConfig();
    client = createClient<paths>({
      baseUrl: config.public.apiBase,
      credentials: "include",
    });
  }
  return client;
}

/** Gateway origin, for login redirects and connection URLs. */
export function apiBase(): string {
  return useRuntimeConfig().public.apiBase.replace(/\/$/, "");
}

/** Redirect the browser to the gateway OIDC login and back to `path`. */
export function gotoLogin(path?: string) {
  const next = `${window.location.origin}${path ?? window.location.pathname}`;
  window.location.href = `${apiBase()}/login?next=${encodeURIComponent(next)}`;
}
