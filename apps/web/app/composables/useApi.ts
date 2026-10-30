import createClient from "openapi-fetch";
import type { paths } from "~~/types/api";

let client: ReturnType<typeof createClient<paths>> | null = null;

/** Typed client for the management API (generated types, cookie auth). */
export function useApi() {
  if (!client) {
    const config = useRuntimeConfig();
    client = createClient<paths>({
      baseUrl: config.public.apiBase,
      credentials: "include",
    });
    client.use({
      async onResponse({ response }) {
        await handleSessionResponse(response);
        return response;
      },
    });
  }
  return client;
}

/**
 * A management-API call the typed client cannot make, such as a POST answered
 * with an event stream, with the same cookie and the same session handling.
 */
export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${apiBase()}${path}`, { ...init, credentials: "include" });
  await handleSessionResponse(response);
  return response;
}

/**
 * What every management-API answer means for the session. A session that
 * expired mid-visit answers 401 on the next call; the browser goes back through
 * login instead of showing a failed request. A 403 is a known user who may not
 * do this: when they were demoted since the page loaded, the catalogue is all
 * they can use now. A 403 for any other reason (a refused origin check) is left
 * to the caller to show as the error it is.
 */
async function handleSessionResponse(response: Response): Promise<void> {
  if (response.status === 401) {
    gotoLogin();
  } else if (response.status === 403 && !(await stillAdmin())) {
    window.location.assign("/catalogue");
  }
}

/** Whether the signed-in user is still an administrator, asked fresh from the gateway. */
async function stillAdmin(): Promise<boolean> {
  const me = await fetch(`${apiBase()}/api/v1/me`, { credentials: "include" });
  if (!me.ok) return true; // not knowable; leave the page as it is
  return Boolean((await me.json()).is_admin);
}

/** Gateway origin, for login redirects and connection URLs. */
export function apiBase(): string {
  return useRuntimeConfig().public.apiBase.replace(/\/$/, "");
}

/** The redirect URI an upstream's OAuth provider sends a person back to after sign-in. */
export function upstreamCallbackUrl(): string {
  return `${apiBase()}/oauth/upstream/callback`;
}

/** Redirect the browser to the gateway OIDC login and back to `path`. */
export function gotoLogin(path?: string) {
  const next = `${window.location.origin}${path ?? window.location.pathname}`;
  window.location.href = `${apiBase()}/login?next=${encodeURIComponent(next)}`;
}
