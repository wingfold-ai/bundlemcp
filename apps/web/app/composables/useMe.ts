export interface Me {
  kind: "admin" | "user" | "service";
  email?: string | null;
  display_name?: string | null;
  is_admin: boolean;
}

const me = ref<Me | null>(null);
const checked = ref(false);

/** Session state (UI-2): null when not signed in; kind "user" means no access. */
export function useMe() {
  async function refresh(): Promise<Me | null> {
    const config = useRuntimeConfig();
    const resp = await fetch(`${config.public.apiBase}/api/v1/me`, {
      credentials: "include",
    });
    me.value = resp.ok ? await resp.json() : null;
    checked.value = true;
    return me.value;
  }
  return { me, checked, refresh };
}
