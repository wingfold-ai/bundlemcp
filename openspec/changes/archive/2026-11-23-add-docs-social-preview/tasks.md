# Tasks

## 1. Preview image (DOC-19)

- [x] 1.1 Add the image source in `docs/.vitepress/og-image/og.html` and `tools/render_og_image.py`, which renders it
  at 1200×630 into `docs/public/og-image.png`. Verify that running the script writes the PNG.
- [x] 1.2 Add `test_doc19_the_preview_image_is_1200_by_630` under `packages/bundlemcp/tests/infrastructure/`, reading
  the PNG header. Verify that it passes.

## 2. Tags (DOC-19)

- [x] 2.1 In `docs/.vitepress/config.ts`, add the shared Open Graph and Twitter tags to `head`, and `og:title`,
  `og:description` and `og:url` per page through `transformHead`. Verify with `cd docs && npm run build` that
  `dist/guide/quickstart.html` and `dist/index.html` carry the tags the spec's scenarios name.
- [x] 2.2 Add `test_doc19_every_page_gets_preview_tags`, checking that the config declares each tag. Verify that it
  passes.
- [x] 2.3 In `docs/README.md`, say what the preview image is and how to regenerate it. Verify that
  `uv run rumdl check .` and `python3 tools/check_docs_links.py` pass.

## 3. Gates

- [x] 3.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` docs scripts, `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`. No DTO
  or route changes, so `npm run openapi` is not needed.
