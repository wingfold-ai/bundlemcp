# Spec Delta

## ADDED Requirements

### Requirement: AUTH-38 Operator templates for the browser pages
The browser pages the gateway renders itself (the consent screen, the page returning a browser to its client, the
pages ending an upstream connect, and the page refusing a deactivated account) MUST be replaceable by an operator
without rebuilding the gateway. When `BUNDLEMCP_AUTH_PAGES_TEMPLATE_DIR` names a directory, a page whose template file
name is found there is rendered from that file, and every other page from the built-in template; a template there may
include or extend other files in the same directory. Every value a page is given is HTML-escaped in an override as in
the built-in page. A template that refers to a value its page is not given is an error, not an empty string.

At startup, before the gateway serves a request, every page MUST be loaded, compiled and rendered once with sample
values; a page that fails stops the start with an error naming the template. A setting that names no existing
directory stops the start too. The values each page receives, and what an override must keep (on the consent screen:
a form posting to the given action with the given token and an `approve` or `deny` action), are documented for
operators ([Branding the sign-in pages](../../../docs/self-hosting/auth-pages.md)). Without the setting, every page is
rendered exactly as before.

#### Scenario: One page is overridden
- **GIVEN** a template directory holding only `consent.html`
- **WHEN** a signed-in user reaches the consent screen, and an upstream connect then completes
- **THEN** the consent screen is rendered from the operator's file, and the connect page from the built-in template

#### Scenario: Consent still approves and denies
- **GIVEN** an overridden `consent.html` that keeps the form contract
- **WHEN** the user approves one authorization and denies another
- **THEN** the first reaches the client's redirect URI with a code and the second with `error=access_denied`

#### Scenario: Values stay escaped
- **WHEN** an overridden page renders a client name holding `<script>`
- **THEN** the page carries it as `&lt;script&gt;`

#### Scenario: A broken override stops the start
- **WHEN** the gateway starts with a template directory holding a `consent.html` that does not compile, or that
  refers to a value the consent screen is not given
- **THEN** the gateway does not start, and the error names `consent.html`

#### Scenario: No template directory
- **WHEN** the setting is unset
- **THEN** every page's body is identical to the built-in rendering

### Requirement: AUTH-39 Operator assets for the browser pages
When `BUNDLEMCP_AUTH_PAGES_ASSET_DIR` names a directory, the gateway MUST serve its files read-only, without
authentication, at `/auth-pages/assets/<path>`, so the browser pages can load stylesheets, fonts and images from the
gateway's own origin. A template builds such a URL with `asset_url('<path>')`. Only a regular file inside the directory
whose extension is one of `css`, `woff2`, `woff`, `ttf`, `otf`, `svg`, `png`, `jpg`, `jpeg`, `gif`, `webp`, `avif` or
`ico` is served, with the content type of that extension, `Cache-Control: public, max-age=3600`,
`X-Content-Type-Options: nosniff` and a CSP of `default-src 'none'; style-src 'unsafe-inline'; sandbox`, so a file
opened on its own (an SVG) runs no script. Anything else answers `404`: a directory (there is no listing), a hidden file
or directory (a path segment starting with `.`), another extension, a missing file, and a path that leaves the
directory, whether by `..`, an absolute path or a symbolic link pointing outside. Without the setting the route does not
exist, and `asset_url` is an error that stops the start when a page uses it. A setting that names no existing directory
stops the start.

#### Scenario: An asset is served
- **GIVEN** an asset directory holding `brand/logo.svg`
- **WHEN** a browser requests `/auth-pages/assets/brand/logo.svg`
- **THEN** it receives the file with `Content-Type: image/svg+xml` and `Cache-Control: public, max-age=3600`

#### Scenario: Traversal is refused
- **WHEN** a request asks for `/auth-pages/assets/../secret.css`, its percent-encoded form, or a symbolic link in the
  directory that points outside it
- **THEN** the gateway answers `404` and serves nothing from outside the directory

#### Scenario: No listing and no other types
- **WHEN** a request names a directory inside the asset directory, a hidden file, or a file with an unlisted extension
- **THEN** the gateway answers `404`

#### Scenario: No asset directory
- **WHEN** the setting is unset
- **THEN** `/auth-pages/assets/<anything>` answers `404`
