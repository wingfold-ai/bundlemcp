import { defineConfig, type HeadConfig } from "vitepress";
import { requirementsLedgerPlugin } from "./requirements-ledger";

// Cookieless Plausible analytics on the published site only: the publish
// workflow sets both variables from repository variables, so local builds, CI
// and forks load no tracking script. The standard script ignores localhost.
const plausibleDomain = process.env.DOCS_PLAUSIBLE_DOMAIN;
const plausibleScript = process.env.DOCS_PLAUSIBLE_SCRIPT_URL;
const analytics: HeadConfig[] =
  plausibleDomain && plausibleScript
    ? [["script", { defer: "", "data-domain": plausibleDomain, src: plausibleScript }]]
    : [];

// The site's public address: the sitemap lists every page under it.
const siteUrl = "https://bundlemcp.com";

// The user-facing documentation site (the documentation spec). Architecture material in
// docs/arc42, docs/adr and docs/likec4 stays out of the site: it is written
// for contributors, links into openspec/, and is read on GitHub.
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
  // /requirements.json, fetched by the Requirements page (docs/reference/requirements.md)
  vite: { plugins: [requirementsLedgerPlugin()] },
  lastUpdated: true,
  sitemap: { hostname: siteUrl },
  head: [["link", { rel: "icon", type: "image/svg+xml", href: "/logo-mark.svg" }], ...analytics],
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
          { text: "bundlemcp vs. FastMCP", link: "/guide/bundlemcp-vs-fastmcp" },
          { text: "Upstream server settings", link: "/guide/upstream-server-settings" },
          { text: "Authentication", link: "/guide/authentication" },
          { text: "Glossary", link: "/guide/glossary" },
        ],
      },
      {
        text: "Self-hosting",
        items: [
          { text: "Local, tunnel or production", link: "/self-hosting/setups" },
          { text: "Requirements", link: "/self-hosting/requirements" },
          { text: "Production deployment", link: "/self-hosting/deploy" },
          { text: "Configuration", link: "/self-hosting/configuration" },
          { text: "Identity provider", link: "/self-hosting/identity-provider" },
          { text: "Bootstrap file", link: "/self-hosting/bootstrap" },
          { text: "Operations", link: "/self-hosting/operations" },
          { text: "Troubleshooting", link: "/self-hosting/troubleshooting" },
        ],
      },
      {
        text: "Manage the gateway",
        items: [
          { text: "Upstream servers", link: "/manage/servers" },
          { text: "Bundles and tool curation", link: "/manage/bundles" },
          { text: "Endpoints", link: "/manage/endpoints" },
          { text: "API keys", link: "/manage/api-keys" },
          { text: "Users and consents", link: "/manage/users" },
          { text: "Audit log", link: "/manage/audit" },
          { text: "Export and import", link: "/manage/export-import" },
          { text: "Inspector", link: "/manage/inspector" },
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
          { text: "Error responses", link: "/integrate/errors" },
          { text: "Metering hook", link: "/integrate/metering-hook" },
          { text: "Identity for upstream servers", link: "/integrate/upstream-identity" },
          { text: "HTTP surface reference", link: "/integrate/http-surface" },
        ],
      },
      {
        text: "Reference",
        items: [{ text: "Requirements", link: "/reference/requirements" }],
      },
    ],
    socialLinks: [{ icon: "github", link: "https://github.com/wingfold-ai/bundlemcp" }],
    editLink: {
      pattern: "https://github.com/wingfold-ai/bundlemcp/edit/main/docs/:path",
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
