# Tasks

## 1. In progress from openspec/changes

- [x] 1.1 Add `docs/.vitepress/roadmap-changes.ts`. Its Vite plugin provides `virtual:roadmap-changes`: one entry per
  active change, with name, first sentence of the "Why", checked and total tasks, and a proposal URL only when
  `repositoryPublic` is set. The dev server watches `openspec/changes/`. Register the plugin in `config.ts`. Verify by
  running `npm run dev` with a scratch change and seeing it appear, then disappear once the change is moved under
  `archive/` (DOC-17).

## 2. The metro line

- [x] 2.1 Add `docs/.vitepress/theme/RoadmapLine.vue` and register it in `theme/index.ts`. Its stations come from props
  and In progress from the virtual module, with an empty state. It is horizontal on wide screens and vertical below
  1200 px, styled with the brand tokens. Verify by viewing it at desktop and phone widths in light and dark mode.
- [x] 2.2 Write `docs/roadmap.md`. The frontmatter holds the stations:
  - **Now (v0.4 public preview).** Bundles and curation, per-client endpoints, OAuth with any OIDC provider, per-user
    upstream credentials, audit log, export/import and bootstrap, metering hook, multi-replica sessions. Each links its
    docs page.
  - **Next (v0.5 tool integrity).** Detect and warn, review before serving, temporary deactivation.
  - **Then (v1.0).** metamcp importer, v1.0 scope.
  - **Later.** ChatGPT search/fetch profile, PyPI package, metrics.

  The body opens with one paragraph, "the control point between your AI clients and your MCP servers: one login,
  curated tools, nothing changes behind your back." It then holds the component, "What bundlemcp won't do" linking the
  decision log, and "Have a say" naming GitHub Discussions (Ideas). Add "Roadmap" to the top navigation in
  `config.ts`. Verify that `npm run build` in `docs/` passes with no dead links (DOC-16).

## 3. Release step

- [x] 3.1 Add the roadmap step after the numbered list in "How a release happens" in `CONTRIBUTING.md`. Verify that
  `uv run rumdl check CONTRIBUTING.md` passes.

## 4. Gates

- [x] 4.1 `cd docs && npm run build`, private (no `DOCS_REPOSITORY_PUBLIC`): the build passes. The built
  `roadmap.html` holds no link into the repository, the five stations and the empty state; the size check stays under
  9 MiB.
- [x] 4.2 Run the gates and verify each passes:
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `uv run rumdl check .`
  - `uv run lint-imports`
  - `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and `check_adr_graph.py`
  - `python3 tools/check_spec_ids.py`
  - `openspec validate --all --strict`
