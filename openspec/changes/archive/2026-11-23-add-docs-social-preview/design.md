# Design

## Context

The docs site is VitePress (`docs/.vitepress/config.ts`). It already names its public address in `siteUrl` for the
sitemap, and puts the favicon and analytics in `head`. See proposal.md for why.

## Goals / Non-Goals

**Goals:** one preview image for the whole site; correct per-page title, description and URL.

**Non-Goals:** an image per page. Generating images at build time would add a headless browser to the docs build for
little gain, since most shares point at the home page or the quickstart.

## Decisions

**Shared tags in `head`, per-page tags in `transformHead`.** `og:image`, its size and alt text, `og:site_name`,
`og:type` and the Twitter card are the same on every page, so they sit in `head`. `transformHead` receives each page's
resolved title and description and adds `og:title`, `og:description` and `og:url`. The URL is built from `siteUrl` and
the page's clean path (`index.md` becomes the directory, `.md` is dropped), matching `cleanUrls` and the sitemap.

**The image is a committed PNG, rendered from HTML.** The source is an HTML page in `docs/.vitepress/og-image/` that
uses the logo files from `docs/public/`. `tools/render_og_image.py` renders it with Playwright at 1200×630 into
`docs/public/og-image.png`. It is run by hand when the design changes, not in CI, so the docs build stays free of a
browser. The alternative, an SVG image, is not accepted by LinkedIn and X as a preview image.

**Absolute URLs.** Crawlers do not resolve relative `og:image` paths reliably, so the image and page URLs are
absolute, on `siteUrl`.

## Risks / Trade-offs

- [Preview caches] LinkedIn and others cache a preview for days → after deploying, refresh it once with LinkedIn's
  Post Inspector.
- [The image drifts from the brand] → its source and render command are in the repository and documented in
  `docs/README.md`.
