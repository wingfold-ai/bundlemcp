import { defineConfig } from "vitepress";

// The user-facing documentation site (spec 61). Architecture material in
// docs/arc42, docs/adr and docs/likec4 stays out of the site: it is written
// for contributors, links into spec/, and is read on GitHub.
export default defineConfig({
  title: "bundlemcp",
  description:
    "Self-hostable MCP bundling gateway: register MCP servers, compose bundles, expose per-client endpoints.",
  lang: "en-US",
  srcExclude: ["arc42/**", "adr/**", "likec4/**", "**/README.md"],
  cleanUrls: true,
  // syntax palette with green-teal tones that sit next to the brand accent
  markdown: { theme: { light: "vitesse-light", dark: "vitesse-dark" } },
  // <likec4-view> is the web component generated from docs/likec4 at build time
  vue: { template: { compilerOptions: { isCustomElement: (tag) => tag.startsWith("likec4-") } } },
  ignoreDeadLinks: "localhostLinks",
  lastUpdated: true,
  head: [["link", { rel: "icon", type: "image/svg+xml", href: "/logo-mark.svg" }]],
  themeConfig: {
    logo: { light: "/lockup-light.svg", dark: "/lockup-dark.svg", alt: "bundlemcp" },
    siteTitle: false,
    nav: [
      { text: "Guide", link: "/guide/what-is-bundlemcp", activeMatch: "/guide/" },
      { text: "Self-hosting", link: "/self-hosting/deploy", activeMatch: "/self-hosting/" },
      { text: "Manage", link: "/manage/servers", activeMatch: "/manage/" },
      { text: "Connect clients", link: "/connect/claude", activeMatch: "/connect/" },
      { text: "Integrate", link: "/integrate/management-api", activeMatch: "/integrate/" },
    ],
    sidebar: [
      {
        text: "Guide",
        items: [
          { text: "What is bundlemcp?", link: "/guide/what-is-bundlemcp" },
          { text: "Quickstart", link: "/guide/quickstart" },
          { text: "Core concepts", link: "/guide/concepts" },
          { text: "Authentication", link: "/guide/authentication" },
          { text: "Roles and identity", link: "/guide/roles-and-identity" },
        ],
      },
      {
        text: "Self-hosting",
        items: [
          { text: "Production deployment", link: "/self-hosting/deploy" },
          { text: "Configuration", link: "/self-hosting/configuration" },
          { text: "Identity provider", link: "/self-hosting/identity-provider" },
          { text: "Bootstrap file", link: "/self-hosting/bootstrap" },
          { text: "Operations", link: "/self-hosting/operations" },
        ],
      },
      {
        text: "Manage the gateway",
        items: [
          { text: "Servers", link: "/manage/servers" },
          { text: "Bundles and tool curation", link: "/manage/bundles" },
          { text: "Endpoints", link: "/manage/endpoints" },
          { text: "API keys", link: "/manage/api-keys" },
          { text: "Users and consents", link: "/manage/users" },
          { text: "Audit log", link: "/manage/audit" },
        ],
      },
      {
        text: "Connect clients",
        items: [
          { text: "claude.ai", link: "/connect/claude" },
          { text: "ChatGPT", link: "/connect/chatgpt" },
          { text: "Scripts and agents", link: "/connect/scripts" },
          { text: "stdio servers behind a sidecar", link: "/connect/stdio-sidecar" },
        ],
      },
      {
        text: "Integrate",
        items: [
          { text: "Management API", link: "/integrate/management-api" },
          { text: "Metering hook", link: "/integrate/metering-hook" },
          { text: "Identity for upstream servers", link: "/integrate/upstream-identity" },
          { text: "HTTP surface reference", link: "/integrate/http-surface" },
        ],
      },
    ],
    socialLinks: [{ icon: "github", link: "https://github.com/mhoegger/bundlemcp" }],
    editLink: {
      pattern: "https://github.com/mhoegger/bundlemcp/edit/main/docs/:path",
      text: "Edit this page on GitHub",
    },
    search: { provider: "local" },
    outline: { level: [2, 3] },
    footer: {
      message: "Specs, architecture records and diagrams live in the repository.",
      copyright: "bundlemcp",
    },
  },
});
