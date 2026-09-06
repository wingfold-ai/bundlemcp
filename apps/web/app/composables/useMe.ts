import type { components } from "~~/types/api";

export type Me = components["schemas"]["MeRead"];

/** Session state (UI-2): null when not signed in; kind "user" means no access. */
export function useMe() {
  // useState keeps the identity per request/app instance, never across visitors
  const me = useState<Me | null>("me", () => null);
  const checked = useState<boolean>("me-checked", () => false);

  async function refresh(): Promise<Me | null> {
    const { data, response } = await useApi().GET("/api/v1/me");
    me.value = response.ok && data ? data : null;
    checked.value = true;
    return me.value;
  }
  return { me, checked, refresh };
}
