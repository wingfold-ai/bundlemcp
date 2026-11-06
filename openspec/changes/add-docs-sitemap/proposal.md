# Proposal

## Why

The documentation site is about to go public, and it should be registered in Google Search Console. The site has no
`sitemap.xml` and no `robots.txt`, so there is nothing to submit and crawlers have to find every page by following
links. The site's "Last updated" dates are also wrong: the publish workflow checks out a single commit, so every page
shows the date of the latest push.

## What Changes

- The published site serves `/sitemap.xml`, listing the canonical `https://bundlemcp.com` URL of every page it
  publishes, and `/robots.txt`, which allows crawling and names that sitemap.
- Each page's last-modified date, shown on the page and in the sitemap, comes from the last commit that changed that
  page.
- The CI `docs` job checks that the built sitemap lists every built page and nothing else, and that `robots.txt`
  names the sitemap.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documentation`: adds DOC-13 (search-engine discovery of the published site).

## Impact

- `docs/.vitepress/config.ts` (sitemap), `docs/public/robots.txt` (new).
- `.github/workflows/publish-docs.yml`: full history in the checkout, so page dates are right.
- `.github/workflows/ci.yml` and a new `tools/check_docs_sitemap.py` for the check.
- `docs/README.md`: the publishing section names the sitemap and robots file.
- No gateway code, DTO or route changes; no ADR (no architectural decision).
