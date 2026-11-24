import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { createContentLoader } from "vitepress";

// The blog under docs/blog: what a post must declare, which posts are drafts,
// and the published posts newest first. The index page, the feed and llms.txt
// all read posts through postsLoader(), so they always agree.

export const BLOG_TITLE = "bundlemcp blog";
// the canonical short text about bundlemcp, word for word
export const BLOG_DESCRIPTION =
  "Self-hostable MCP gateway that bundles all your MCP servers into one connector for any MCP client or AI tool, with one login and curated tools.";

// A post's `author` must be a name listed here; the author line links the profile.
export const AUTHORS: Record<string, string> = {
  "Marius Högger": "https://www.linkedin.com/in/marius-h%C3%B6gger",
};

export interface Post {
  url: string;
  title: string;
  description: string;
  date: string;
  author: string;
  authorLink: string;
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const POST_PAGE = /^blog\/[^/]+\.md$/;

/** Whether a page, by its path inside docs/, is a blog post (the index is not one). */
export function isPostPage(relativePath: string): boolean {
  return POST_PAGE.test(relativePath) && relativePath !== "blog/index.md";
}

export function isDraft(frontmatter: Record<string, unknown>): boolean {
  return frontmatter.draft === true;
}

/**
 * A post's date as YYYY-MM-DD, or undefined when it has none or a malformed one.
 * YAML reads an unquoted 2026-11-24 as a timestamp at midnight UTC.
 */
export function postDate(value: unknown): string | undefined {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.toISOString().slice(0, 10);
  }
  if (typeof value === "string" && DATE.test(value)) return value;
  return undefined;
}

/** The post a page's frontmatter declares; throws, naming the page, when a field is wrong. */
export function readPost(frontmatter: Record<string, unknown>, url: string, page: string): Post {
  const problems: string[] = [];
  const text = (key: string): string => {
    const value = frontmatter[key];
    if (typeof value === "string" && value.trim()) return value;
    problems.push(`no ${key}`);
    return "";
  };
  const title = text("title");
  const description = text("description");
  const author = text("author");
  const date = postDate(frontmatter.date);
  if (!date) problems.push("no date of the form YYYY-MM-DD");
  if (author && !(author in AUTHORS)) {
    problems.push(`author "${author}" is not one of ${Object.keys(AUTHORS).join(", ")}`);
  }
  if (problems.length) throw new Error(`Blog post ${page}: ${problems.join("; ")}`);
  return { url, title, description, date: date!, author, authorLink: AUTHORS[author] };
}

/**
 * The blog sources marked `draft: true`, as paths inside docs/. Read before
 * VitePress parses anything, so it looks only for that literal frontmatter line.
 */
export function draftSources(docsDir: string): string[] {
  const blogDir = join(docsDir, "blog");
  return readdirSync(blogDir)
    .filter((name) => name.endsWith(".md") && name !== "index.md")
    .filter((name) => {
      const frontmatter = /^---\n([\s\S]*?)\n---\n/.exec(readFileSync(join(blogDir, name), "utf8"));
      return frontmatter !== null && /^draft:\s*true\s*$/m.test(frontmatter[1]);
    })
    .map((name) => `blog/${name}`);
}

/** The published posts, newest first; drafts are left out, a malformed post throws. */
export function postsLoader() {
  return createContentLoader("blog/*.md", {
    transform(pages): Post[] {
      return pages
        .filter((page) => page.url !== "/blog/" && !isDraft(page.frontmatter))
        .map((page) => readPost(page.frontmatter, page.url, page.url))
        .sort((a, b) => b.date.localeCompare(a.date) || a.title.localeCompare(b.title));
    },
  });
}
