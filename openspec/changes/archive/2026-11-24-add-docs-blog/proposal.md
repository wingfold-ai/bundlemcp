# Proposal

## Why

Posts about bundlemcp need a home the project owns. On bundlemcp.dev they sit on the same domain as the docs, keep
their address when platforms change, and give posts elsewhere one place to link to. The site has no place for dated
writing today: every page is reference documentation in the sidebar.

## What Changes

- A blog at `/blog/`, linked as "Blog" in the top navigation before "Roadmap". Posts are Markdown files in
  `docs/blog/<slug>.md` with `title`, `description`, `date` (`YYYY-MM-DD`) and `author` frontmatter, and an optional
  `draft: true`.
- The blog index lists published posts newest first, each with its date, title and description, built from the posts
  themselves rather than a hand-kept list. With no published posts it says so in one sentence.
- A post page shows its title, date and an author line linking the author's profile, and links back to the index.
  Blog pages have no sidebar.
- An RSS 2.0 feed at `/blog/feed.xml`, written by the build, announced on every page with an RSS autodiscovery link.
- Drafts are left out of the production build: no page, no index entry, no feed item, no sitemap entry, no
  `llms.txt` line. The local dev server still shows them, marked as drafts.
- Published posts are ordinary pages for discovery: they are in the sitemap, carry their own description and link
  preview tags (as articles, with their publication date), and `llms.txt` and `llms-full.txt` list them in a Blog
  section.
- A post missing a required field, with a malformed date or an unknown author fails the build and the hermetic tests.
- Only the blog's infrastructure lands in the repository. Posts are added one by one, each in its own pull request.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documentation`: adds DOC-22 (a blog with an RSS feed).

## Impact

- `docs/blog/index.md` and a content loader beside it; `docs/.vitepress/blog-posts.ts` (post fields, drafts, the
  feed); a post header component in `docs/.vitepress/theme/`.
- `docs/.vitepress/config.ts`: the nav item, the autodiscovery link, drafts excluded from production builds, no
  sidebar on blog pages, article link-preview tags, and the feed written in `buildEnd`.
- `docs/.vitepress/llms-txt.ts`: a Blog section of published posts.
- `docs/package.json`: the `feed` package as a dev dependency, to write RSS.
- `tools/check_docs_blog.py`, a CI step in the `docs` job, and tests under `packages/bundlemcp/tests/infrastructure/`;
  `tools/check_docs_links.py` accepts the link to the feed, a file only the build writes.
- `docs/README.md`: how to write a post.
- No gateway behaviour changes. No ADR.
