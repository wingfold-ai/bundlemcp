# Tasks

## 1. Sitemap, robots file and the CI check (DOC-13)

- [x] 1.1 In `docs/.vitepress/config.ts`, set `sitemap: { hostname: "https://bundlemcp.com" }` from a named
  constant. Verify that `cd docs && npm run build` writes `docs/.vitepress/dist/sitemap.xml` with clean URLs and no
  `404` entry.
- [x] 1.2 Add `docs/public/robots.txt`: allow every user agent and name `https://bundlemcp.com/sitemap.xml`. Verify
  that it lands in `docs/.vitepress/dist/`.
- [x] 1.3 Write `tools/check_docs_sitemap.py`: the sitemap's `<loc>` set must equal the URLs derived from the built
  `.html` files (without `404.html`), all on `https://bundlemcp.com`, and `robots.txt` must name the sitemap. Error
  messages name the page and cite DOC-13. Run it in the CI `docs` job after the build. Verify that it passes on the
  build, and fails when a page is removed from `sitemap.xml` and when `robots.txt` loses its `Sitemap` line.
- [x] 1.4 Add hermetic tests for the check's URL derivation and comparison, named for DOC-13, under
  `packages/bundlemcp/tests/infrastructure/`. Verify that `uv run pytest -q` passes.

## 2. Page dates from history (DOC-13)

- [x] 2.1 Give the checkout in `.github/workflows/publish-docs.yml` `fetch-depth: 0`. Verify on a full local clone
  that the sitemap's `lastmod` values differ between pages changed at different times.
- [x] 2.2 In `docs/README.md`, say in the publishing section that the build writes `sitemap.xml`, that `robots.txt`
  names it, and why the publish checkout fetches full history. Verify that `uv run rumdl check .` and
  `python3 tools/check_docs_links.py` pass.

## 3. Verification

- [x] 3.1 Run the gates: `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`,
  the four `tools/check_docs_*.py`/`check_adr_graph.py` scripts, `python3 tools/check_spec_ids.py` and
  `openspec validate --all --strict`. No DTO or route changes, so `npm run openapi` is not needed.
