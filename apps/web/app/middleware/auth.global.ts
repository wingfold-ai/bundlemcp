// every route requires a signed-in user. Anonymous visitors go to the
// gateway OIDC login; signed-in non-admins only ever see the catalogue.
export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return;

  const { me, checked, refresh } = useMe();
  if (!checked.value) await refresh();

  if (!me.value) {
    gotoLogin(to.fullPath);
    return abortNavigation();
  }
  if (!me.value.is_admin && !to.path.startsWith("/catalogue")) {
    return navigateTo("/catalogue");
  }
});
