# Tasks

## 1. Posts, index and post page (DOC-22)

- [x] 1.1 Add `docs/.vitepress/blog-posts.ts` (authors table, post field checks, draft detection, the shared loader
  transform) and `docs/blog/posts.data.ts`. Verify with a build.
- [x] 1.2 Add `docs/blog/index.md` (description built from the canonical short text) rendering the posts newest first,
  or one sentence when there are none. Verify with a build that `dist/blog/index.html` shows the sentence.
- [x] 1.3 Add the `BlogPostHeader` theme component in the `doc-before` slot; in the config, turn off sidebar, aside
  and prev/next on blog pages, validate post fields in `transformPageData`, and add "Blog" to the nav before
  "Roadmap". Verify with a temporary post that its page shows title, date, author line and the back link, and that a
  post without a date fails the build.
- [x] 1.4 Exclude drafts from production builds through `srcExclude`. Verify that a temporary `draft: true` post has no
  built page and no sitemap entry.
- [x] 1.5 Add `test_doc22_*` hermetic tests: post frontmatter, nav order, autodiscovery link. Verify that they pass.

## 2. Feed and discovery (DOC-22)

- [x] 2.1 Add `feed` to `docs/package.json` and write `/blog/feed.xml` in `buildEnd`; add the RSS autodiscovery link to
  the shared head. Verify that the built feed parses as RSS 2.0 and lists a temporary post.
- [x] 2.2 Move `og:type` into `transformHead`, with `article`, `article:published_time` and `article:author` for posts.
  Verify on a built post page, and that `test_docs_social_preview.py` passes.
- [x] 2.3 Add a `## Blog` section of published posts to `llms.txt` and their Markdown to `llms-full.txt`, and list the
  blog index under Optional. Verify with a temporary post.
- [x] 2.4 Add `tools/check_docs_blog.py` and its CI step in the `docs` job. Verify that it passes with a temporary
  published post and with it as a draft, and fails when a draft's page is built.
- [x] 2.5 Document writing a post in `docs/README.md`. Verify with `uv run rumdl check .`.

## 3. Gates

- [x] 3.1 Delete every temporary post. Run `npm run build` in `docs/`, `uv run pytest -q`, `uv run ruff check .`,
  `uv run rumdl check .`, `uv run lint-imports`, the `tools/check_*.py` docs scripts (with `check_docs_blog.py` and
  `check_docs_sitemap.py` on the build), `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`. No
  DTO or route changes, so `npm run openapi` is not needed.
