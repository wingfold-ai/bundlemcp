// Wireframe admin UI (spec 60). SPA: the gateway owns all state; this app is
// an optional container (UI-5) talking to /api/v1 with the admin session cookie.
export default defineNuxtConfig({
  ssr: false,
  modules: ["@nuxt/ui"],
  devtools: { enabled: false },
  css: ["~/assets/css/main.css"],
  runtimeConfig: {
    public: {
      // Origin of the gateway; overridden via NUXT_PUBLIC_API_BASE
      apiBase: "http://localhost:8000",
    },
  },
});
