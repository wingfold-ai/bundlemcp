// UI-7: the upstream server pages moved from /servers to /upstreams. Old
// bookmarks and links in older documentation land on the same page, with the
// rest of the path, the query and the hash kept.
export default defineNuxtRouteMiddleware((to) => {
  if (to.path === "/servers" || to.path.startsWith("/servers/")) {
    return navigateTo(
      { path: `/upstreams${to.path.slice("/servers".length)}`, query: to.query, hash: to.hash },
      { replace: true },
    );
  }
});
