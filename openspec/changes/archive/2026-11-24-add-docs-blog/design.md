# Design

## Context

The docs are VitePress 1.6 (`docs/.vitepress/config.ts`). Each page's `description` frontmatter feeds its meta
description and `og:description` (DOC-19, DOC-20); the sitemap is VitePress's own, built from the rendered pages
(DOC-13); `llms.txt` is written in `buildEnd` from the sidebar (DOC-21). The site is static and uploaded by FTP
(DOC-6), so anything the blog needs, the feed included, must be a file in the build output. See proposal.md for why.
This change touches only `docs/`, the CI `docs` job and tests; no gateway layer is involved.

## Goals / Non-Goals

**Goals:** adding a post is adding one Markdown file; a draft can be committed and previewed without being published.

**Non-Goals:** tags, categories, pagination, comments, per-post images, an Atom or JSON feed. Each can come later
without changing the post format.

## Decisions

**Posts are found with `createContentLoader`, not a hand-kept list.** `docs/blog/posts.data.ts` loads `blog/*.md`
(the index excluded), drops drafts, checks the fields and sorts newest first; the index page renders that data. The
feed and `llms.txt` load the same pattern with the same transform in `buildEnd`, so the three cannot disagree. The
rules (required fields, date format, known authors, what a draft is) live once in `docs/.vitepress/blog-posts.ts`.

**Drafts are excluded through `srcExclude` in production.** The content loader does not apply `srcExclude`, so drafts
are also filtered in the loader's transform; but leaving them out of `srcExclude` would still build their pages and
put them in the sitemap. The config therefore scans `docs/blog/*.md` for `draft: true` when it is loaded and adds
those files to `srcExclude` when `NODE_ENV` is `production`, which `vitepress build` sets before it reads the config.
`vitepress dev` keeps them, and the post header marks them "Draft". The scan reads only the frontmatter line, with no
YAML parser, because the config cannot import VitePress's internal one.

**The post header is a theme slot, not Markdown in each post.** A `BlogPostHeader` component in the `doc-before` slot
renders the link back to `/blog/`, the title, the date and the author line on every page under `blog/` except the
index. Posts therefore have no `# heading` of their own; `llms-full.txt` prefixes the title so their Markdown still
starts with one. `transformPageData` sets `sidebar: false`, `aside: false` and no prev/next links on blog pages, and
validates a post's fields so a bad post fails the build at the page that has it.

**Authors are a table in `blog-posts.ts`.** It maps the name in `author` to a profile URL; today one entry, Marius
Högger and his LinkedIn profile. An unknown name fails the build instead of rendering an unlinked line.

**The feed is written with the `feed` package.** It is small, has no runtime footprint on the site, and produces
valid RSS 2.0; hand-writing XML would mean owning its escaping. Item dates are the post date at 00:00 UTC. The feed
carries descriptions, not full text: post Markdown links into the site with root-relative paths, which a feed reader
would resolve against the wrong host.

**Link previews mark posts as articles.** `og:type` moves from the shared head into `transformHead`, so a post gets
`article` with `article:published_time` and `article:author`, and every other page keeps `website`. The site-wide RSS
autodiscovery link goes in the shared head.

**A CI check reads the built site.** `tools/check_docs_blog.py` parses `dist/blog/feed.xml` as RSS 2.0, compares its
items with the built post pages and with the Blog section of `dist/llms.txt`, and checks that no draft source has a
built page, a sitemap entry, a feed item or an `llms.txt` line. It finds drafts by the same literal line the build
does, so it needs no YAML parser on the CI runner. Hermetic tests check the post frontmatter, the nav order and the
autodiscovery link, and read each post with a YAML parser to confirm that the literal-line detection agrees with it.

## Risks / Trade-offs

- [A draft's file name is visible in the public repository] → drafts are meant for previewing a post close to
  publication; work in progress stays in the second brain, as the project's content rules already say.
- [The draft scan matches only a literal `draft: true` line] → the documented form; a hermetic test reads every post
  with a YAML parser and fails when YAML's reading of `draft` and the literal-line scan disagree.
- [The dev server's draft marking is not covered by a test] → it is a preview aid only; the production behaviour
  that matters (a draft is not published) is checked in CI on every build.
- [The FTP upload never deletes] → a post published and later turned back into a draft keeps its old HTML file on
  the host until removed by hand; the sitemap, feed and index stop naming it at once.
