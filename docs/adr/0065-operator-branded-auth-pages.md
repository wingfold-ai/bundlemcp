# ADR-0065: Operators brand the auth pages with templates and same-origin assets

**Status:** accepted · **Date:** 2026-11-17 · **Amends:** [ADR-0014](0014-gateway-rendered-oauth-authlib.md)

## Context

ADR-0014 made the consent screen, and the few other pages the OAuth flows need, minimal Jinja templates rendered by
the gateway itself, under the SEC-6 hardening headers. Those templates ship inside the image, and their policy,
`default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action …`, loads no file at all. A
deploying application that puts its own name on the sign-in flow therefore cannot change what the consent screen
says or how it looks without rebuilding the gateway image, and cannot use its own fonts or logo even then.

The consent screen is the page where a person decides whether to trust a client, and the one page of the flow that
the deploying application does not otherwise control. Two questions follow: how an operator replaces a page, and
where the page's stylesheets, fonts and images may come from without weakening the policy that protects it.

## Decision drivers

- No rebuild: a mounted directory and an environment variable are enough.
- Partial overrides: replacing the consent screen must not mean copying the four other pages.
- A broken template must fail the start, not a person's sign-in.
- The pages' policy stays as tight as possible, and does not change at all for a deployment that does not brand.
- The flows' security must not depend on the operator's HTML: a consent page that drops its form fails closed.

## Decision

- **Templates by file name.** `BUNDLEMCP_AUTH_PAGES_TEMPLATE_DIR` names a directory searched before the built-in
  templates (a Jinja `ChoiceLoader`: the directory's `FileSystemLoader`, then the package's `PackageLoader`). A page
  whose file name is there is rendered from it; the rest stay built in. Autoescape stays on, and undefined variables
  are errors (`StrictUndefined`).
- **Checked at startup.** The composition root builds the pages (`AuthPages`, in `api/oauth/pages/`) as its first
  step and renders every page once with sample values for its documented variables. A page that fails stops the
  start, naming the file, before the database or Valkey is opened.
- **Assets from the gateway's own origin.** `BUNDLEMCP_AUTH_PAGES_ASSET_DIR` names a directory served read-only at
  `/auth-pages/assets/` by a `Controller` mounted only when the setting is present and kept out of the OpenAPI
  document. Only an allow-list of stylesheet, font and image extensions is served, each with an explicit content type,
  `nosniff`, a one-hour cache lifetime and a sandboxing policy; directories, hidden files and paths that leave the
  directory (`..`, absolute, or by symbolic link) are not found. Templates build URLs with `asset_url('…')`.
- **`'self'`, only with assets.** While an asset directory is configured, the page policy becomes
  `default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; frame-ancestors 'none'`
  plus the unchanged `form-action`. Without one, it is byte-for-byte what it was.
- **The settings are read in the composition root only.** The module-level environment and headers are replaced by
  one object on the container, reached through a provider, like every other collaborator.

## Alternatives considered

- **Admit an operator-named origin (a CDN, a font service) in the policy.** It would let a page load from anywhere the
  operator lists, but it moves the consent page's trust boundary to a host the gateway does not control, needs a
  validator for operator-written source expressions, and leaks every consent page view to that host. Copying the
  files into a directory keeps the policy at `'self'`.
- **Starlette `StaticFiles` on the app.** It confines paths, but it serves every file type, `.html` included, from the
  gateway's origin, and it is a second way to mount routes beside `Controller.mount` (ADR-0026).
- **A theming layer instead of templates** (a few variables: colours, a logo URL, a product name). Less to get wrong,
  but the consumer wants its own wording and layout; any fixed set of knobs would be outgrown, and the template
  contract is no larger than the variables each page already receives.
- **Compile only at startup, without a sample render.** It catches syntax errors but not a misspelt variable or an
  `asset_url` call without an asset directory, both of which would then fail the first real sign-in.
- **Render the pages in the admin web app.** It would give the pages the web app's styling, but bring back the
  dependency ADR-0014 removed: the OAuth flow would need the web app running and same-origin with the gateway.

## Consequences

### Positive

- A deploying application brands the consent screen, and any other page, with a mounted directory.
- A broken override is found at deploy time, with the file named, and never by a person signing in.
- Deployments that do not brand see no change at all: same pages, same headers, no new route.

### Trade-offs

- The gateway cannot check that an override keeps the consent form's contract. A page that drops it fails safe (no
  valid token, nothing but `approve` grants), and the contract is documented, but the operator can still ship a page
  that does not work.
- What the consent screen says is now the operator's to decide, including saying something misleading. That is within
  the trust an operator already holds by running the gateway.
- Templates are read at startup, so changing one needs a restart; assets are read per request and change at once,
  subject to the one-hour browser cache.
- Asset names are not fingerprinted, so a replaced file can be stale in a browser for up to an hour; a new file name
  avoids it.
