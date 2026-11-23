# Tasks

## 1. Descriptions (DOC-20)

- [x] 1.1 Add a `description` to the frontmatter of every published page under `docs/`, at most 160 characters, using
  the target searches from the keyword research; give `docs/index.md` a `title` that names bundlemcp as an MCP
  gateway. Verify with a build that `dist/guide/quickstart.html` carries its own description.
- [x] 1.2 Make the site-wide description in `docs/.vitepress/config.ts` client-neutral.
- [x] 1.3 Add `test_doc20_every_page_has_its_own_description` under `packages/bundlemcp/tests/infrastructure/`.
  Verify that it passes, and fails for a page without a description.

## 2. llms.txt (DOC-21)

- [x] 2.1 Add `docs/.vitepress/llms-txt.ts` and call it from `buildEnd` in the config. Verify with a build that
  `dist/llms.txt` and `dist/llms-full.txt` match the spec's scenarios.
- [x] 2.2 Add `test_doc21_llms_txt_follows_the_sidebar`, checking that the generator is wired into the build and
  that every sidebar link points at an existing page. Verify that it passes.
- [x] 2.3 Name the two files in the publishing section of `docs/README.md`. Verify that `uv run rumdl check .` and
  `python3 tools/check_docs_links.py` pass.

## 3. Gates

- [x] 3.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the
  `tools/check_*.py` docs scripts, `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`. No DTO
  or route changes, so `npm run openapi` is not needed.
