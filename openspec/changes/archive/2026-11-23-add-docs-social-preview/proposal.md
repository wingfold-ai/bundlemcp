# Proposal

## Why

When someone shares a bundlemcp.dev link on LinkedIn, Slack, X or in a chat, the preview shows no image, and its title
and description are guessed from the page. The site has no Open Graph or Twitter card tags. A link card for the
project on a LinkedIn profile therefore shows up without a picture next to cards that have one, and shared links get
less attention than they could.

## What Changes

- Every page of the published site carries Open Graph and Twitter card tags: the page's own title, description and
  canonical URL, the site name, and one shared preview image.
- The preview image is a 1200×630 PNG at `https://bundlemcp.dev/og-image.png`. It shows the logo, the headline
  "One gateway for all your MCP servers" and a small servers-to-bundle-to-endpoint diagram.
- The image's source is kept in the repository with a command to regenerate it, so it can change with the brand.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documentation`: adds DOC-19 (link previews for the published site).

## Impact

- `docs/.vitepress/config.ts`: the shared tags in `head`, the per-page ones from `transformHead`.
- `docs/public/og-image.png`, and its source in `docs/.vitepress/og-image/` with `tools/render_og_image.py`.
- `docs/README.md`: how to regenerate the image.
- A hermetic test of the image's size and of the tags in the config.
- No gateway behaviour changes. No ADR.
