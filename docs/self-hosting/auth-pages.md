# Branding the sign-in pages

During OAuth the gateway renders a few browser pages itself. The one people see most is the **consent screen**, where
they approve a client such as claude.ai for an endpoint. Out of the box these pages are plain and say "bundlemcp". You
can replace any of them with your own wording, layout, fonts, colours and logo, without rebuilding the image: mount a
directory of templates, and optionally a directory of assets, and point two settings at them.

| Variable | What it does |
|---|---|
| `BUNDLEMCP_AUTH_PAGES_TEMPLATE_DIR` | Templates here replace the built-in pages by file name. |
| `BUNDLEMCP_AUTH_PAGES_ASSET_DIR` | Files here are served at `/auth-pages/assets/…` for the pages to load. |

Both are optional and independent. With neither set, the pages, their headers and the gateway's routes are exactly as
they were. Both are described in [Configuration](configuration.md#sign-in-pages) too.

## The pages

| File | Shown when | Variables it receives |
|---|---|---|
| `consent.html` | A signed-in person authorises a client for an endpoint for the first time | `client_name`, `endpoint_name`, `bundle_name`, `scope`, `token`, `consent_action`, `user_email` |
| `return_to_client.html` | The consent answer cannot be a redirect, because the client's redirect URI cannot be written into the page's security policy; the page links to the client instead | `client_name`, `heading`, `location` |
| `connected.html` | An upstream connect (an upstream server's own sign-in) has completed | `server_name` |
| `connect_refused.html` | An upstream connect was finished in a browser or account that did not start it | none |
| `account_deactivated.html` | Someone signs in whose account an administrator has deactivated | none |

What the variables hold:

- `client_name`: the name the client registered, for example "Claude".
- `endpoint_name`, `bundle_name`: the endpoint being authorised and the bundle it serves.
- `scope`: the requested scope.
- `user_email`: the signed-in person's email, or their user id if the identity provider gave none.
- `token`: the one-time token of this consent request.
- `consent_action`: the URL the consent form posts to (`/oauth/consent`).
- `heading`: "Access granted" or "Access denied".
- `location`: the client's redirect URI, with the code or the error, that the link must lead to.
- `server_name`: the name of the upstream server that was connected.

Every page can also call `asset_url('path/in/asset/dir')`, which returns the URL of a file in the asset directory, for
example `/auth-pages/assets/brand/logo.svg`.

Every value is HTML-escaped, in your templates as in the built-in ones; write `{{ client_name }}`, never
`{{ client_name | safe }}`, because the client chooses its own name. A variable a page does not receive is an error,
not an empty string.

## What an override must keep

The gateway cannot check what your HTML means, only that it renders, so keep these by hand:

**`consent.html`** must keep a form that posts to `consent_action` with the token and an `action` field:

```html
<form method="post" action="{{ consent_action }}">
  <input type="hidden" name="token" value="{{ token }}">
  <button type="submit" name="action" value="deny">Deny</button>
  <button type="submit" name="action" value="approve">Approve</button>
</form>
```

- `method="post"`, and the action exactly `{{ consent_action }}`: the page's security policy lets the form post nowhere
  else.
- The hidden `token` field with `{{ token }}`. It is single-use and expires after ten minutes; without it the gateway
  refuses the answer.
- An `action` field whose value is `approve` to grant. Any other value, or none, denies. The buttons may say anything.
- Show at least `client_name` and `endpoint_name`, so the person knows what they are approving.

A consent page that loses the form fails closed: nothing is granted, and the person sees an error instead of being
returned to the client.

**`return_to_client.html`** must keep a link to `{{ location }}`, which is how the person gets back to the client.

The other three pages carry no form and no required link.

Two more constraints apply to every page:

- **No scripts.** The security policy refuses every script, inline or not, with or without assets. Pages are HTML and
  CSS only.
- **Nothing from other origins.** Stylesheets, fonts and images load only from the asset directory, never from a CDN
  or a font service. Copy the files you need into the asset directory.

## Templates

Templates are [Jinja](https://jinja.palletsprojects.com/templating/). Only the files you want to change go into the
directory; any page without a file there keeps the built-in template. A template may `{% extends %}` or
`{% include %}` other files from the same directory, so the pages can share a layout:

```text
templates/
├── layout.html
├── consent.html
└── connected.html
```

```html
<!-- layout.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Example{% endblock %}</title>
  <link rel="stylesheet" href="{{ asset_url('site.css') }}">
</head>
<body>
  <img class="logo" src="{{ asset_url('logo.svg') }}" alt="Example">
  <main>{% block body %}{% endblock %}</main>
</body>
</html>
```

```html
<!-- consent.html -->
{% extends "layout.html" %}
{% block title %}Connect {{ client_name }}{% endblock %}
{% block body %}
  <h1>Connect {{ client_name }} to your Example account?</h1>
  <p>{{ client_name }} will be able to use the tools of <b>{{ endpoint_name }}</b> as you ({{ user_email }}).</p>
  <form method="post" action="{{ consent_action }}">
    <input type="hidden" name="token" value="{{ token }}">
    <button type="submit" name="action" value="deny">Not now</button>
    <button type="submit" name="action" value="approve">Connect</button>
  </form>
{% endblock %}
```

The built-in templates are a good starting point: they are in the image under
`bundlemcp/api/oauth/pages/templates/` in the Python package, and in the repository at
`packages/bundlemcp/bundlemcp/api/oauth/pages/templates/`.

### Checked at start-up

When the gateway starts, it loads every page and renders it once with sample values, before it serves any request. A
template that does not compile, uses a variable its page does not receive, or calls `asset_url` while no asset
directory is set stops the start with an error naming the file, for example:

```text
BrokenAuthPage: auth page consent.html (/etc/bundlemcp/templates/consent.html) failed its startup check:
UndefinedError: 'client_nmae' is undefined
```

So a broken template shows up when you deploy, not when someone tries to sign in. Templates are read only at start-up:
restart the gateway after changing one.

## Assets

The asset directory holds the files your templates load. They are served without authentication, read-only, at
`/auth-pages/assets/<path inside the directory>`; build the URL with `asset_url('<path>')` rather than writing it out.

Only these file types are served, each with its own content type:

| Kind | Extensions |
|---|---|
| Stylesheets | `.css` |
| Fonts | `.woff2`, `.woff`, `.ttf`, `.otf` |
| Images | `.svg`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.avif`, `.ico` |

Everything else answers `404`: other file types (`.html` and `.js` included), directories (there is no listing),
hidden files and anything in a hidden directory (a name starting with `.`), and any path that would leave the
directory, including through a symbolic link that points outside it.

Responses may be cached by browsers for an hour (`Cache-Control: public, max-age=3600`). Assets are read from disk on
each request, so a changed file is served at once, but a browser that already has it may show the old one for up to
an hour; give a file a new name when the change cannot wait. A stylesheet's own `url(…)` references, to fonts or
images, are relative to the stylesheet, so `url(fonts/brand.woff2)` in `site.css` loads
`/auth-pages/assets/fonts/brand.woff2`.

### Content Security Policy

The pages carry a strict Content-Security-Policy. Without an asset directory it is:

```text
default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'
```

With `BUNDLEMCP_AUTH_PAGES_ASSET_DIR` set, the gateway's own origin is added for stylesheets, fonts and images, and
nothing else:

```text
default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; frame-ancestors 'none'; form-action 'self'
```

On the consent screen, `form-action` also names the client's redirect URI, so the browser may follow the answer to the
client. Inline `<style>` keeps working either way. A template directory on its own does not change the policy, so
templates without assets are limited to inline styles.

## Deploying

Mount both directories read-only into the gateway container and set the variables to the paths as the container sees
them:

```yaml
services:
  gateway:
    environment:
      BUNDLEMCP_AUTH_PAGES_TEMPLATE_DIR: /etc/bundlemcp/auth-pages/templates
      BUNDLEMCP_AUTH_PAGES_ASSET_DIR: /etc/bundlemcp/auth-pages/assets
    volumes:
      - ./auth-pages/templates:/etc/bundlemcp/auth-pages/templates:ro
      - ./auth-pages/assets:/etc/bundlemcp/auth-pages/assets:ro
```

A path that is not an existing directory stops the start. Every replica needs the same files.

If your reverse proxy sends only some paths to the gateway and the rest to the admin UI on the same host, add
`/auth-pages/*` to the gateway's paths, beside `/oauth/*` and `/login`; otherwise the assets reach the admin UI and
are not found.
