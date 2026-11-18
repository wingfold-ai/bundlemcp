# Tasks

## 1. Settings

- [x] 1.1 Add `auth_pages_template_dir` and `auth_pages_asset_dir` (`DirectoryPath | None`, described for operators)
  to `Settings`. Test that a path that is not an existing directory is refused when the settings load (AUTH-38,
  AUTH-39).

## 2. Page rendering (AUTH-38)

- [x] 2.1 Add `AuthPage` (the five template names, each with its sample values) and replace the module-level
  environment with `page_templates(override_dir)`: a `ChoiceLoader` of the override directory and the package,
  autoescape on, `StrictUndefined`.
- [x] 2.2 Add `AuthPages` with `render`, `headers`, `verify` and the `auth_pages(settings)` factory, and an
  `asset_url` global that raises without an asset directory.
- [x] 2.3 Build and verify it first in `CompositionRoot._compose()`, publish it as `AppContainer.auth_pages`, add
  `AuthPagesProvider`, and move the three controllers onto it. Remove `PAGE_TEMPLATES` and `PAGE_HEADERS`.
- [x] 2.4 Tests: default rendering identical to the plain package environment; one override replaces one page while
  the others fall back; values stay escaped; a syntax error and an unknown variable in an override each stop the
  start naming the file; the controllers pass exactly each page's sample variable names; consent approves and denies
  through an overridden template.

## 3. Assets and policy (AUTH-39, SEC-6)

- [x] 3.1 Add `assets` to `page_headers`, writing `'self'` into `style-src`, `font-src` and `img-src`.
- [x] 3.2 Add `AuthPageAsset`, the media-type table and `AuthPages.asset(path)` with its confinement rules.
- [x] 3.3 Add `AuthPageAssetController` (out of the OpenAPI document) and mount it in `create_app` only when an asset
  directory is configured.
- [x] 3.4 Tests: an asset is served with its type and cache headers; `..`, encoded `..`, absolute, hidden, directory,
  unlisted-extension and outside-pointing symlink requests answer `404`; no route without the setting; the CSP holds
  `'self'` only with assets, on the consent page and the other pages.

## 4. Documentation

- [x] 4.1 ADR-0065 (amends ADR-0014), with both ADR indexes regenerated.
- [x] 4.2 `docs/self-hosting/auth-pages.md` with the template contract and an example, linked from the sidebar and
  from `configuration.md`, which lists both variables.
- [x] 4.3 Route `/auth-pages/*` to the gateway in `deploy/proxy/Caddyfile`, and note it for operators who split paths
  between the gateway and the web app.

## 5. Verification

- [x] 5.1 Run the gates: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run rumdl check .`, `uv run lint-imports`, the `tools/check_docs_*.py` scripts, `tools/check_adr_graph.py`,
  `python3 tools/check_spec_ids.py`, `openspec validate --all --strict`, and `cd apps/web && npm run openapi`
  (expected: no change, the asset route is not in the schema).
