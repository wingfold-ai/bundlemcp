# Design

## Context

The docs are VitePress. A page's `description` frontmatter becomes its `<meta name="description">`, and since DOC-19
also its `og:description`; without one, the site-wide `description` in `docs/.vitepress/config.ts` applies. The
sidebar in the same file is the site's table of contents. See proposal.md for why.

## Decisions

**Descriptions live in each page's frontmatter.** They stay next to the text they describe, so whoever rewrites a page
sees its description. A central map in the config was the alternative; it would drift from the pages.

**`llms.txt` follows the sidebar.** The sidebar already groups and orders the pages for a human reader, so the index
reuses it: one `##` section per sidebar group, one link per item. Pages outside the sidebar (the home page, the
roadmap) are listed under `## Optional`, as the llms.txt convention suggests for secondary material. The reference
page of requirements is skipped in `llms-full.txt`, since its content is rendered from data at runtime.

**Generated in `buildEnd`, read from the Markdown sources.** `docs/.vitepress/llms-txt.ts` reads each page's source,
splits off the frontmatter with a small parser for the two keys it needs (`title`, `description`, including a
description folded over several lines), and writes both files into the build output. No new dependency.

**A hermetic test guards the descriptions.** It walks the published pages (the same exclusions the config's
`srcExclude` applies) and checks that each has a description of at most 160 characters and that none repeats.

## Risks / Trade-offs

- [Descriptions go stale when a page changes] → they sit in the page's own frontmatter, and the test catches a
  missing or overlong one; a wrong one is caught in review.
- [llms-full.txt takes 338 KB of the hosting quota] → with it the built site is about 9.2 MB, roughly 220 KB under
  the 9 MiB size check CI runs for the 10 MB plan (DOC-6). Chosen deliberately to ship the full text; if the site
  outgrows the check, dropping `llms-full.txt` or the long reference pages from it is the first relief.
- [llms.txt is a young convention] → it costs one build step and no runtime; if assistants stop reading it, removing
  it is equally small.
