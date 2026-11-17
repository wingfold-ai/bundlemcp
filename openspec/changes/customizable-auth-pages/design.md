# Design

## Context

See [proposal.md](proposal.md). Today:

- The five templates live in `api/oauth/pages/templates/` and are loaded by one module-level Jinja `Environment`
  (`PAGE_TEMPLATES` in `api/oauth/pages/page_templates.py`): a `PackageLoader`, autoescape on for `.html`.
- Three controllers render them: `AuthorizeController` (`consent.html`, `return_to_client.html`), `LoginController`
  (`account_deactivated.html`) and `UpstreamConnectController` (`connected.html`, `connect_refused.html`). Each imports
  the module-level environment and the module-level `PAGE_HEADERS`, or calls `page_headers(form_redirect_source=…)`.
- A template is compiled lazily, on its first render, so a broken one would fail a user's sign-in.
- `page_headers` writes the CSP from one constant, `default-src 'none'; style-src 'unsafe-inline';
  frame-ancestors 'none'`, plus `form-action`.

## Goals / Non-Goals

**Goals:**

- An operator replaces any of the five pages, or only some, by mounting a directory; the rest stay built in.
- Every template that will be rendered is known good before the first request.
- Same-origin stylesheets, fonts and images are possible, and nothing beyond them; the policy does not change for a
  deployment that does not ask for it.
- No module-level state configured from settings: the pages are built once by the composition root and reach the
  controllers through a provider, like every other collaborator.

**Non-Goals:**

- Overriding the admin web app, the login at the identity provider, or JSON error responses.
- Scripts on the pages. `script-src` stays `'none'` (through `default-src`), with or without assets.
- Assets from another origin (a CDN, Google Fonts). An operator copies the files into the asset directory.
- Changing templates or assets without a restart for templates. Templates are compiled at startup; assets are read
  from disk on each request, so a changed asset is served at once (subject to the browser cache).
- Translations, or page variables beyond what each page already receives.

## Decisions

### One `AuthPages` object, built from the settings, owns rendering, headers and assets

`api/oauth/pages/auth_pages.py` holds `AuthPages`, a frozen Pydantic model with the Jinja environment and the optional
asset directory, and its factory `auth_pages(settings)` beside it (module-naming.md). It exposes:

- `render(page: AuthPage, **values) -> str`;
- `headers(*, form_redirect_source: str | None = None) -> dict[str, str]`, which calls `page_headers` with
  `assets=` set from whether an asset directory is configured;
- `asset(path: str) -> AuthPageAsset | None`, the confined file lookup for the asset route;
- `verify()`, which loads, compiles and renders every page with its sample values.

`AuthPage` (`api/oauth/pages/auth_page.py`) is a `StrEnum` of the five template file names, so a controller cannot
name a page that does not exist, and each member carries its `sample_values`: the variables that page receives,
written once. The startup render and the operator documentation both follow it, and a test drives the consent and
return pages through the real flow with overrides that print every variable of their contract.

The composition root calls `auth_pages(settings)` and `verify()` as the first step of `_compose()`, before it opens
the database or Valkey, and publishes the object as `AppContainer.auth_pages`. `api/oauth/providers.py` gains
`AuthPagesProvider`. The module-level `PAGE_TEMPLATES` and `PAGE_HEADERS` are removed; `page_templates.py` keeps the
function that builds the environment.

Layer: all of it is in `api/`, where the templates already are. The settings are read in `main/` only.

Alternatives considered:

- **Keep module-level globals and configure them from the environment at import.** That is configuration read outside
  the composition root, and a test could not build two differently configured apps in one process.
- **Build the object in `create_app`** rather than the lifespan. The container, which providers read, is built in the
  lifespan; building the pages there too keeps one place, and `_compose()` runs before any request, so the failure is
  still at startup (uvicorn exits with "Application startup failed").

### Overrides by file name through a `ChoiceLoader`

`page_templates(override_dir)` builds the environment with
`ChoiceLoader([FileSystemLoader(override_dir), PackageLoader("bundlemcp.api.oauth.pages", "templates")])`, or the
`PackageLoader` alone without a directory. Autoescape stays `select_autoescape(["html"])`. `undefined=StrictUndefined`
makes a misspelt variable an error that the startup render catches, instead of an empty string on the live page;
the built-in templates use only the variables they are given, so their output does not change.

Because the loader resolves every name, an override can `{% extends "layout.html" %}` or `{% include %}` a file of
its own in the same directory, and could even extend a built-in page by name.

Alternatives considered:

- **Compile only, without a sample render.** Compiling catches syntax errors but not an unknown variable or an
  `asset_url` call without assets, which would fail the first real sign-in. Rendering each page with its sample values
  costs a few milliseconds once.
- **Default `Undefined`.** A typo would render an empty string; on the consent screen that could be the client name
  the user is deciding about.

### Assets: a confined lookup, an allow-list of extensions, a controller mounted only when configured

`AuthPageAssetController` (`api/oauth/controllers/auth_page_asset_controller.py`, prefix `/auth-pages/assets`,
`include_in_schema = False`) has one route, `GET /{path:path}`, which calls `AuthPages.asset(path)` and returns a
`FileResponse` or `404`. `create_app` mounts it only when `auth_pages_asset_dir` is set, as it does `/metrics`.

`asset()` refuses, before touching the disk: a path with a backslash or NUL, an absolute path, any segment that is
empty, `.`, `..` or starts with `.`, and an extension outside the media-type table. It then resolves the joined path
(following symbolic links) and serves it only if the result is a regular file inside the resolved asset directory.
The media-type table (`AUTH_PAGE_ASSET_TYPES` in `auth_page_asset.py`) is explicit rather than `mimetypes`, whose
answers depend on the host (`.woff2` is missing on some systems). Responses carry
`Cache-Control: public, max-age=3600`, `X-Content-Type-Options: nosniff` and
`Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`. A policy on a stylesheet, font or
image response changes nothing when a page loads it; it matters only when the file is opened on its own, where it
keeps an SVG from running script. `FileResponse` adds `ETag` and `Last-Modified`.

`asset_url(path)` is a Jinja global returning `/auth-pages/assets/<path>` with each segment percent-encoded. Without
an asset directory it raises, so a template using it fails the startup render with a message naming the setting.
URLs are root-relative, like the consent form's action.

Alternatives considered:

- **Starlette `StaticFiles` mounted on the app.** It does confine paths, but it is not a `Controller` (controllers.md
  requires every HTTP surface to be one), it serves every file type including `.html` from the gateway's origin, and
  it would need `app.mount` beside `Controller.mount`.
- **A CSP that admits an operator-named origin (a CDN).** It moves the trust boundary of the consent page to a host
  the gateway does not control, and needs a source-expression validator for operator input. Copying files into a
  directory is a small price for keeping the policy `'self'`.
- **A long `immutable` cache lifetime.** Asset names are not fingerprinted, so a replaced logo would be stale for a
  year. An hour, plus `ETag`, is a compromise; the docs advise a new file name for an urgent change.

### The CSP gains `'self'` only with assets

`page_headers(*, form_redirect_source=None, assets=False)` writes
`default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; frame-ancestors 'none'`
when `assets` is true, and today's string otherwise; `form-action` is appended as before. `'unsafe-inline'` stays so
an override can keep inline `<style>` as the built-in pages do. Nothing else is admitted: no `script-src`, no
`connect-src`, no `frame-src`.

### Settings

Two `Settings` fields, both `DirectoryPath | None` with default `None`: `auth_pages_template_dir` and
`auth_pages_asset_dir` (`BUNDLEMCP_AUTH_PAGES_TEMPLATE_DIR`, `BUNDLEMCP_AUTH_PAGES_ASSET_DIR`). Pydantic rejects a
path that is not an existing directory when the settings load, before the app is built.

## Risks / Trade-offs

- **An override can drop the consent form's contract** (the token field, the `approve`/`deny` values, the action).
  The gateway cannot check HTML semantics; a broken form fails safe, because a consent post without a valid token is
  refused and nothing other than `approve` grants. The contract is documented, and the startup render proves only that
  the page renders.
- **An override can mislead.** The operator controls what the consent screen says. That is the point of the feature
  and is within the operator's existing trust: they already run the gateway.
- **Asset files are trusted content on the gateway's origin.** The allow-list keeps `.html` and `.js` out, `nosniff`
  stops type confusion, the sandboxing policy keeps an SVG opened on its own from running script, and the asset
  directory is the operator's, not a user's.
- **Templates need a restart to change.** Acceptable for deploy-time branding, and it is what makes the startup check
  meaningful.
