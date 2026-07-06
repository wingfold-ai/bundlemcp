// UI-2: every route requires a signed-in admin; anonymous users go to the
// gateway OIDC login, signed-in non-admins to the no-access page.
export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return;
  if (to.path === "/no-access") return;

  const { me, checked, refresh } = useMe();
  if (!checked.value) await refresh();

  if (!me.value) {
    gotoLogin(to.fullPath);
    return abortNavigation();
  }
  if (!me.value.is_admin) {
    return navigateTo("/no-access");
  }
});
