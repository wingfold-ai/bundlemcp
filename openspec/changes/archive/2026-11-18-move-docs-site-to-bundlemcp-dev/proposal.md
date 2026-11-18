# Proposal

## Why

The documentation site moves from `bundlemcp.com` to `bundlemcp.dev`. Both domains stay attached to the same
Infomaniak hosting, so links to the old address must keep working, and search engines and Plausible must see one
address only.

## What Changes

- `https://bundlemcp.dev` becomes the site's only address: the sitemap, `robots.txt`, the Plausible domain and the
  versioning link in release notes use it.
- `bundlemcp.com`, `www.bundlemcp.com` and `www.bundlemcp.dev` redirect permanently, with path and query, to
  `https://bundlemcp.dev`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documentation`: DOC-13 names `bundlemcp.dev`; adds DOC-15 (one canonical address).

## Impact

- `docs/public/.htaccess`, `docs/public/robots.txt`, `docs/.vitepress/config.ts`, `docs/README.md`.
- `.github/workflows/publish-docs.yml` (Plausible domain), `tools/check_docs_sitemap.py` and its tests,
  `tools/release_notes.py` and `tools/pull_request_release.py` (versioning link).
- Outside the repository: the hosting serves all four names with one certificate (done), and the Plausible site is
  renamed to `bundlemcp.dev`. No gateway code; no ADR.
