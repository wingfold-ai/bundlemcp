# Tasks

## 1. Canonical address (DOC-15)

- [x] 1.1 Add the host-name redirect to `docs/public/.htaccess`, before the HTTPS rule. Verify against `httpd:2.4`
  serving the built site: `.com` and `www` names answer `301` to the same path and query on `https://bundlemcp.dev`
  in one hop, also from plain HTTP, and `bundlemcp.dev` serves `200`.
- [x] 1.2 Set `DOCS_PLAUSIBLE_DOMAIN` to `bundlemcp.dev` in `publish-docs.yml`, and point the versioning link in
  `tools/release_notes.py` and `tools/pull_request_release.py` at `bundlemcp.dev`. Describe the address and the
  redirect in `docs/README.md`. Verify that `git grep bundlemcp.com` finds only the redirect's description.

## 2. Sitemap on the new address (DOC-13)

- [x] 2.1 Change the sitemap host in `config.ts`, `robots.txt`, `tools/check_docs_sitemap.py` and its tests to
  `https://bundlemcp.dev`. Verify that the build's sitemap lists `bundlemcp.dev` URLs and the check passes.

## 3. Verification

- [x] 3.1 Run the gates: `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`,
  the `tools/check_*.py` scripts and `openspec validate --all --strict`.
- [ ] 3.2 After publishing, check the live site: `https://bundlemcp.com/guide/quickstart` answers `301` to
  `https://bundlemcp.dev/guide/quickstart`, and `https://bundlemcp.dev/sitemap.xml` answers `200`.
