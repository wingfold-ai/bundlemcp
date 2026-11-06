# Tasks

## 1. Build setting and link removal (DOC-14)

- [x] 1.1 Add `docs/.vitepress/repository-links.ts` with the repository URL, `repositoryPublic` from
  `DOCS_REPOSITORY_PUBLIC === "true"` and a Markdown core rule that unlinks repository links. Use it in `config.ts`
  for the GitHub icon, edit links, footer line and hero actions, and expose `repositoryPublic` in the theme config.
  Verify that a default build has no `href` into the repository, including in `requirements.json`.
- [x] 1.2 Add `RepositoryNotice.vue`, register it, and place it on the home page, the quickstart and the deployment
  page. Hide the Requirements page's repository links in a private build. Verify that a default build shows the notice
  on exactly those three pages and a `DOCS_REPOSITORY_PUBLIC=true` build shows every link and no notice.

## 2. CI and publishing (DOC-14)

- [x] 2.1 Write `tools/check_docs_repository_links.py` and hermetic tests for both modes in
  `packages/bundlemcp/tests/infrastructure/test_docs_repository_links.py`. Verify that the check fails, naming the
  files, when run in private mode against a public build.
- [x] 2.2 Pass `vars.DOCS_REPOSITORY_PUBLIC` to the docs build and run the check in `ci.yml` and `publish-docs.yml`.
  Document the variable in `docs/README.md`. Verify that `uv run rumdl check .` passes.

## 3. Verification

- [x] 3.1 Run the gates: `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`,
  the `tools/check_*.py` scripts and `openspec validate --all --strict`. No DTO or route changes.
