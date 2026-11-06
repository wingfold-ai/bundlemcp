# Design

## Context

The site is VitePress 1.6, built by `docs/` and uploaded by `publish-docs.yml` to Infomaniak by FTP. VitePress can
write a sitemap itself once it knows the site's hostname, and it adds each page's `lastmod` from the same git
timestamp it uses for "Last updated" (`lastUpdated: true`). The publish workflow's checkout fetches one commit, so
git reports the push's own date for every page. None of this touches the gateway's layers; every piece lives in
`docs/`, `tools/` or `.github/`.

## Goals / Non-Goals

**Goals:** a sitemap and robots file that match the built pages, and dates search engines can trust.

**Non-Goals:** Search Console verification (a DNS record at Infomaniak, outside the repository); removing the
password gate; per-page `noindex` or priorities.

## Decisions

- **VitePress's own sitemap, not a plugin or a hand-written file.** It is generated from the same page list the build
  renders, so it cannot drift from the pages. The hostname `https://bundlemcp.com` is a constant in `config.ts`, the
  same domain the publish workflow gives Plausible; it is not read from the environment, so local and CI builds write
  the same sitemap and the check runs on every pull request.
- **A static `docs/public/robots.txt`.** Three lines; generating it would add code for nothing.
- **Full history in the publish checkout (`fetch-depth: 0`).** The only way for git to know each page's last change.
  The repository is small enough that the extra fetch costs seconds. The CI `docs` job keeps its shallow checkout:
  its dates are never published, and the check compares URLs, not dates.
- **A `tools/check_docs_sitemap.py` gate in the CI `docs` job**, beside the other `check_docs_*` scripts. It derives
  the expected URL of each built `.html` file (`index.html` → `/`, `a/index.html` → `/a/`, `a/b.html` → `/a/b`),
  skips `404.html`, and compares the set with the sitemap's `<loc>` entries in both directions. It also checks that
  `robots.txt` names the sitemap. Alternative: trust VitePress. Rejected because a future `srcExclude` or rewrite
  change would silently drop pages from search.

## Risks / Trade-offs

- [The hostname is hard-coded] → It is the site's domain and changes only with a move, which would touch the publish
  workflow and DNS anyway; the check fails if the sitemap names another host.
- [A sitemap is published while the site still asks for a password] → Harmless: crawlers get `401` for it like for
  every page, and Search Console is fed only after the gate is removed.
