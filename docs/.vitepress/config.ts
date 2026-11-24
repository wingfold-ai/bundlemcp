import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfigWithTheme, type DefaultTheme, type HeadConfig } from "vitepress";
import { FEED_PATH, writeBlogFeed } from "./blog-feed";
import {
  AUTHORS,
  BLOG_TITLE,
  draftSources,
  isDraft,
  isPostPage,
  postDate,
  postsLoader,
  readPost,
} from "./blog-posts";
import { requirementsLedgerPlugin } from "./requirements-ledger";
import { writeLlmsFiles } from "./llms-txt";
import { roadmapChangesPlugin } from "./roadmap-changes";
import { assertStationLinks, type RoadmapStation } from "./roadmap-stations";
import {
  pointsIntoRepository,
  repositoryPublic,
  repositoryUrl,
  unlinkRepository,
} from "./repository-links";

// Cookieless Plausible analytics on the published site only: the publish
// workflow sets both variables from repository variables, so local builds, CI
// and forks load no tracking script. The standard script ignores localhost.
const plausibleDomain = process.env.DOCS_PLAUSIBLE_DOMAIN;
const plausibleScript = process.env.DOCS_PLAUSIBLE_SCRIPT_URL;
const analytics: HeadConfig[] =
  plausibleDomain && plausibleScript
    ? [["script", { defer: "", "data-domain": plausibleDomain, src: plausibleScript }]]
    : [];

// The site's public address: the sitemap lists every page under it, and link
// previews name each page by its address under it.
const siteUrl = "https://bundlemcp.dev";

// Link previews (Open Graph and Twitter cards) share one image on every page;
// tools/render_og_image.py renders it from docs/.vitepress/og-image/og.html.
const previewImage = `${siteUrl}/og-image.png`;
const preview: HeadConfig[] = [
  ["meta", { property: "og:site_name", content: "bundlemcp" }],
  ["meta", { property: "og:image", content: previewImage }],
  ["meta", { property: "og:image:width", content: "1200" }],
  ["meta", { property: "og:image:height", content: "630" }],
  [
    "meta",
    { property: "og:image:alt", content: "bundlemcp: one gateway for all your MCP servers" },
  ],
  ["meta", { name: "twitter:card", content: "summary_large_image" }],
  ["meta", { name: "twitter:image", content: previewImage }],
];

// Feed readers find the blog's RSS feed from any page.
const feedDiscovery: HeadConfig = [
  "link",
  { rel: "alternate", type: "application/rss+xml", title: BLOG_TITLE, href: `${siteUrl}${FEED_PATH}` },
];

// Drafts under docs/blog are rendered by the dev server only: `vitepress build`
// sets NODE_ENV to production before it reads this file.
const docsDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const drafts = process.env.NODE_ENV === "production" ? draftSources(docsDir) : [];

// A page's canonical address: index.md is its directory, other pages drop .md,
// as cleanUrls serves them and the sitemap lists them.
function pageUrl(relativePath: string): string {
  const path = relativePath.replace(/(^|\/)index\.md$/, "$1").replace(/\.md$/, "");
  return `${siteUrl}/${path}`;
}

// The user-facing documentation site (the documentation spec). Architecture material in
// docs/arc42, docs/adr and docs/likec4 stays out of the site: it is written
// for contributors, links into openspec/, and is read on GitHub.
export default defineConfigWithTheme<DefaultTheme.Config & { repositoryPublic: boolean }>({
  title: "bundlemcp",
  description:
    "Self-hostable, open-source MCP gateway: all your MCP servers behind one endpoint, with one login and curated tools, for any MCP client.",
  lang: "en-US",
  srcExclude: ["arc42/**", "adr/**", "likec4/**", "**/README.md", ...drafts],
  cleanUrls: true,
  // syntax palette with green-teal tones that sit next to the brand accent
  markdown: {
    theme: { light: "vitesse-light", dark: "vitesse-dark" },
    // until the repository is public, a link into it would only reach GitHub's 404
    config: (md) => {
      if (!repositoryPublic) unlinkRepository(md);
    },
  },
  // <likec4-view> is the web component generated from docs/likec4 at build time
  vue: { template: { compilerOptions: { isCustomElement: (tag) => tag.startsWith("likec4-") } } },
  ignoreDeadLinks: "localhostLinks",
  // /requirements.json, fetched by the Requirements page (docs/reference/requirements.md),
  // and virtual:roadmap-changes, the roadmap's "In progress" station (docs/roadmap.md)
  vite: { plugins: [requirementsLedgerPlugin(), roadmapChangesPlugin()] },
  lastUpdated: true,
  sitemap: { hostname: siteUrl },
  // the home page's GitHub button, likewise
  transformPageData(pageData) {
    const stations = pageData.frontmatter.stations as RoadmapStation[] | undefined;
    if (stations) assertStationLinks(stations, pageData.relativePath);
    const actions = pageData.frontmatter.hero?.actions as { link?: string }[] | undefined;
    if (!repositoryPublic && actions) {
      pageData.frontmatter.hero.actions = actions.filter((a) => !pointsIntoRepository(a.link));
    }
    // blog pages: no sidebar, outline or prev/next; a post's header reads the
    // normalised date and the author's profile link from its frontmatter
    if (pageData.relativePath.startsWith("blog/")) {
      Object.assign(pageData.frontmatter, { sidebar: false, aside: false, prev: false, next: false });
    }
    if (isPostPage(pageData.relativePath)) {
      const frontmatter = pageData.frontmatter;
      if (isDraft(frontmatter)) {
        frontmatter.date = postDate(frontmatter.date);
        frontmatter.authorLink = AUTHORS[frontmatter.author as string];
      } else {
        const post = readPost(frontmatter, pageUrl(pageData.relativePath), pageData.relativePath);
        Object.assign(frontmatter, { date: post.date, authorLink: post.authorLink });
      }
    }
  },
  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: "/logo-mark.svg" }],
    ...preview,
    feedDiscovery,
    ...analytics,
  ],
  // /llms.txt and /llms-full.txt (the sidebar's pages and the published posts,
  // for AI assistants) and the blog's RSS feed
  async buildEnd(siteConfig) {
    const posts = await postsLoader().load();
    await writeLlmsFiles(siteConfig, siteUrl, posts);
    await writeBlogFeed(siteConfig.outDir, siteUrl, posts);
  },
  transformHead({ pageData, title, description }) {
    const head: HeadConfig[] = [
      ["meta", { property: "og:title", content: title }],
      ["meta", { property: "og:description", content: description }],
      ["meta", { property: "og:url", content: pageUrl(pageData.relativePath) }],
    ];
    const { date, authorLink } = pageData.frontmatter;
    if (isPostPage(pageData.relativePath) && date) {
      head.push(
        ["meta", { property: "og:type", content: "article" }],
        ["meta", { property: "article:published_time", content: date }],
      );
      if (authorLink) head.push(["meta", { property: "article:author", content: authorLink }]);
    } else {
      head.push(["meta", { property: "og:type", content: "website" }]);
    }
    return head;
  },
  themeConfig: {
    logo: { light: "/lockup-light.svg", dark: "/lockup-dark.svg", alt: "bundlemcp" },
    siteTitle: false,
    nav: [
      { text: "Guide", link: "/guide/what-is-bundlemcp", activeMatch: "/guide/" },
      { text: "Self-hosting", link: "/self-hosting/deploy", activeMatch: "/self-hosting/" },
      { text: "Manage", link: "/manage/servers", activeMatch: "/manage/" },
      { text: "Connect clients", link: "/connect/claude", activeMatch: "/connect/" },
      { text: "Integrate", link: "/integrate/management-api", activeMatch: "/integrate/" },
      { text: "Blog", link: "/blog/", activeMatch: "/blog/" },
      { text: "Roadmap", link: "/roadmap" },
    ],
    sidebar: [
      {
        text: "Guide",
        items: [
          { text: "What is bundlemcp?", link: "/guide/what-is-bundlemcp" },
          { text: "Quickstart", link: "/guide/quickstart" },
          { text: "Core concepts", link: "/guide/concepts" },
          { text: "bundlemcp vs. FastMCP", link: "/guide/bundlemcp-vs-fastmcp" },
          { text: "Coming from metamcp", link: "/guide/coming-from-metamcp" },
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
          { text: "Branding the sign-in pages", link: "/self-hosting/auth-pages" },
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
    repositoryPublic,
    socialLinks: repositoryPublic ? [{ icon: "github", link: repositoryUrl }] : [],
    editLink: repositoryPublic
      ? { pattern: `${repositoryUrl}/edit/main/docs/:path`, text: "Edit this page on GitHub" }
      : undefined,
    search: { provider: "local" },
    outline: { level: [2, 3] },
    footer: {
      message: repositoryPublic
        ? "Specs, architecture records and diagrams live in the repository."
        : undefined,
      copyright: "bundlemcp",
    },
  },
});
