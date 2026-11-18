# Proposal

## Why

The gateway renders five browser pages itself during OAuth: the consent screen, the page that returns a browser to a
client, the two pages that end an upstream connect, and the page that refuses a deactivated account. They are built
into the image, styled as bundlemcp, and their policy loads no file, so a deploying application that puts its own name
on the sign-in flow can change neither their wording nor their look without rebuilding the gateway image. The consent
screen is the page that matters most: it is where a person decides whether to trust a client, and it is the one page
of the flow that does not look like the application they signed up to.

## What Changes

- An optional template directory (`BUNDLEMCP_AUTH_PAGES_TEMPLATE_DIR`). A page whose file name is found there is
  rendered from that file; every other page falls back to the built-in template. Output stays HTML-escaped. Every page
  is loaded, compiled and rendered once with sample values at startup, so a broken override stops the gateway with an
  error naming the file instead of failing the first sign-in.
- An optional asset directory (`BUNDLEMCP_AUTH_PAGES_ASSET_DIR`) for stylesheets, fonts and images, served read-only
  under `/auth-pages/assets/` with a content type per file extension and a one-hour cache lifetime. Only files of the
  listed types inside the directory are served; directories, hidden files and paths that leave it are not found.
- While the asset directory is configured, the pages' policy admits same-origin stylesheets, fonts and images
  (`'self'` in `style-src`, `font-src` and `img-src`). `default-src 'none'`, `frame-ancestors 'none'` and the
  `form-action` rules stay as they are. With neither setting, pages, headers and routes are unchanged.
- A documented template contract: the variables each page receives, the `asset_url()` function that builds an asset
  URL, and what an override must keep for the page's form and links to work.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: adds AUTH-38 (operator templates for the browser pages) and AUTH-39 (operator assets for those pages). The
  codes AUTH-35 to AUTH-37 were reserved by an earlier change and stay unused, so they are skipped.
- `security`: SEC-6 (the browser pages' policy admits same-origin stylesheets, fonts and images while an asset
  directory is configured).

## Impact

- **Gateway:** the auth page rendering in `api/oauth/pages/` becomes an object built from the settings at startup and
  handed to the controllers; a new public, unauthenticated asset route in `api/oauth/controllers/`, mounted only when
  an asset directory is configured and kept out of the OpenAPI document; two new `Settings` fields.
- **Decision:** [ADR-0065](../../../docs/adr/0065-operator-branded-auth-pages.md) (amends ADR-0014): the pages are
  operator-overridable templates, and the gateway serves their assets from its own origin rather than admitting another
  origin in the policy.
- **Docs:** a new operator page, `docs/self-hosting/auth-pages.md`, with the template contract; the two variables in
  `docs/self-hosting/configuration.md`; the development proxy (`deploy/proxy/Caddyfile`) routes `/auth-pages/*` to
  the gateway.
- **Compatibility:** none broken. Without either variable nothing changes; the asset route does not exist.
- **Resolves:** no GitHub issue.
