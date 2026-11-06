// Links into the source repository, which only work once it is public.
import type MarkdownIt from "markdown-it";
import type Token from "markdown-it/lib/token.mjs";

export const repositoryUrl = "https://github.com/wingfold-ai/bundlemcp";

// The publish workflow sets DOCS_REPOSITORY_PUBLIC from the repository variable of the
// same name; any other value, including none, builds the site without repository links.
export const repositoryPublic = process.env.DOCS_REPOSITORY_PUBLIC === "true";

export function pointsIntoRepository(href: string | null | undefined): boolean {
  return href === repositoryUrl || Boolean(href?.startsWith(`${repositoryUrl}/`));
}

/** Keeps the text of every Markdown link into the repository and drops the link itself. */
export function unlinkRepository(md: MarkdownIt): void {
  md.core.ruler.push("unlink_repository", (state) => {
    for (const block of state.tokens) {
      if (block.type !== "inline" || !block.children) continue;
      const kept: Token[] = [];
      const dropping: boolean[] = [];
      for (const token of block.children) {
        if (token.type === "link_open") {
          const drop = pointsIntoRepository(token.attrGet("href"));
          dropping.push(drop);
          if (drop) continue;
        } else if (token.type === "link_close") {
          if (dropping.pop()) continue;
        }
        kept.push(token);
      }
      block.children = kept;
    }
  });
}
