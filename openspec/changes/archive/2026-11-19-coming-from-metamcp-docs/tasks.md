# Tasks

## 1. The metamcp facts

- [x] 1.1 Pick the current metamcp release and read its documentation and README for servers (and their transports),
  namespaces, tool overrides and turning tools off, endpoints and their URLs, API keys (header and query parameter),
  middleware and OAuth. Note each fact with the URL it came from in the pull request description, and verify that
  every row of the mapping table in 2.2 rests on one.

## 2. The page

- [x] 2.1 Write `docs/snippets/metamcp-migration.yaml`, the worked example from design.md: three upstreams (Streamable
  HTTP, a stdio server behind a sidecar, a static API-key header), one bundle with two renamed tools and one hidden
  tool, an `oauth_only` endpoint and an `api_key` endpoint. Each part carries a comment naming the metamcp setting it
  replaces. Add `test_doc18_the_metamcp_migration_example_applies` to
  `packages/bundlemcp/tests/infrastructure/test_bootstrap.py`: it applies the file with the bootstrap runner and checks
  the three upstreams, the bundle with its curation and the two endpoints. Verify that it passes (DOC-18).
- [x] 2.2 Write `docs/guide/coming-from-metamcp.md`:
  - the note naming the metamcp release from 1.1;
  - the concept mapping table, with links into metamcp's documentation;
  - "What bundlemcp leaves out", one entry per decision-log item a metamcp user would notice, each with what to do
    instead;
  - "Moving a setup over", which includes the example with `<<< @/snippets/metamcp-migration.yaml` and names the
    importer as a roadmap theme, linking `/roadmap`;
  - "What you gain", each item linking its docs page.

  Verify that `npm run build` in `docs/` passes, and that the built page shows the included example (DOC-18).
- [x] 2.3 Add the page to the Guide sidebar in `docs/.vitepress/config.ts`, after "bundlemcp vs. FastMCP". Verify that
  the built site's sidebar lists it, and that a site search for "metamcp" finds it (DOC-18).

## 3. Links to the page

- [x] 3.1 Link the page from the README's metamcp row and from the roadmap's "What bundlemcp won't do" section, and add
  "check the Coming from metamcp page against the current metamcp release" to the release checklist in
  CONTRIBUTING.md, next to the roadmap check. Verify that `python3 tools/check_docs_links.py` passes and the docs build
  reports no dead link.

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`,
  `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and `check_adr_graph.py`,
  `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`. No DTO or route changes, so
  `npm run openapi` is not needed. All pass.
