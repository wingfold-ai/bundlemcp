import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { DefaultTheme, SiteConfig } from "vitepress";
import type { Post } from "./blog-posts";

// Writes /llms.txt and /llms-full.txt (https://llmstxt.org) into the build output.
// llms.txt is the site's name and description, then one section per sidebar
// group listing its pages as links with their descriptions, then the published
// blog posts newest first under "Blog"; pages outside the sidebar go under
// "Optional". llms-full.txt is the Markdown of the same pages, in the same
// order, each headed by its URL.

// Pages outside the sidebar that an assistant may still want.
const OPTIONAL = [
  { text: "Home", link: "/" },
  { text: "Roadmap", link: "/roadmap" },
  { text: "Blog", link: "/blog/" },
];

// Rendered from data at runtime, so its Markdown says nothing useful.
const NO_FULL_TEXT = new Set(["/reference/requirements", "/blog/"]);

interface Page {
  title: string;
  link: string;
  url: string;
  description: string;
  body: string;
}

interface Section {
  name: string;
  pages: Page[];
}

/** The frontmatter keys this file needs, and the Markdown after it. */
function splitFrontmatter(source: string): { meta: Record<string, string>; body: string } {
  const match = /^---\n([\s\S]*?)\n---\n/.exec(source);
  if (!match) return { meta: {}, body: source };
  const meta: Record<string, string> = {};
  // a key line, then the indented lines a value is folded over
  for (const entry of match[1].matchAll(/^(\w+): (.*(?:\n {2}.*)*)/gm)) {
    let value = entry[2]
      .split("\n")
      .map((line) => line.trim())
      .join(" ");
    if (value.startsWith('"') && value.endsWith('"')) value = JSON.parse(value);
    meta[entry[1]] = value;
  }
  return { meta, body: source.slice(match[0].length).trim() };
}

function sourceFile(link: string): string {
  if (link.endsWith("/")) return `${link.replace(/^\//, "")}index.md`;
  return `${link.replace(/^\//, "")}.md`;
}

async function readPage(srcDir: string, siteUrl: string, text: string, link: string): Promise<Page> {
  const { meta, body } = splitFrontmatter(await readFile(join(srcDir, sourceFile(link)), "utf8"));
  const heading = /^# (.+)$/m.exec(body);
  const title = meta.title ?? heading?.[1] ?? text;
  return {
    title,
    link,
    url: `${siteUrl}${link}`,
    description: meta.description ?? "",
    // a blog post's title is its frontmatter's, so its Markdown has no heading
    body: heading ? body : `# ${title}\n\n${body}`,
  };
}

export async function writeLlmsFiles(
  siteConfig: SiteConfig,
  siteUrl: string,
  posts: Post[],
): Promise<void> {
  const { srcDir, outDir, site } = siteConfig;
  const sidebar = (site.themeConfig as DefaultTheme.Config).sidebar as DefaultTheme.SidebarItem[];
  const groups = [
    ...sidebar.map((group) => ({ name: group.text ?? "", items: group.items ?? [] })),
    { name: "Blog", items: posts.map((post) => ({ text: post.title, link: post.url })) },
    { name: "Optional", items: OPTIONAL },
  ];
  const sections: Section[] = [];
  for (const group of groups) {
    const pages: Page[] = [];
    for (const item of group.items) {
      if (item.link) pages.push(await readPage(srcDir, siteUrl, item.text ?? "", item.link));
    }
    if (pages.length) sections.push({ name: group.name, pages });
  }

  const index = [`# ${site.title}`, "", `> ${site.description}`, ""];
  for (const section of sections) {
    index.push(`## ${section.name}`, "");
    for (const page of section.pages) {
      const description = page.description ? `: ${page.description}` : "";
      index.push(`- [${page.title}](${page.url})${description}`);
    }
    index.push("");
  }
  await writeFile(join(outDir, "llms.txt"), index.join("\n"));

  const full: string[] = [];
  for (const page of sections.flatMap((section) => section.pages)) {
    if (NO_FULL_TEXT.has(page.link)) continue;
    full.push(`<!-- Source: ${page.url} -->`, "", page.body, "", "---", "");
  }
  await writeFile(join(outDir, "llms-full.txt"), full.join("\n"));
}
