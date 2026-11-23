# Spec Delta

## ADDED Requirements

### Requirement: DOC-19 Link previews
Every page of the published documentation site MUST carry Open Graph and Twitter card tags, so a shared link shows a
proper preview. The title, description and URL are the page's own, the URL being its canonical
`https://bundlemcp.dev` address. The image is one shared 1200×630 PNG served at `https://bundlemcp.dev/og-image.png`,
announced with its size and a text alternative, and the Twitter card is `summary_large_image`.

#### Scenario: A shared page shows its own title and the preview image
- **WHEN** the page `/guide/quickstart` of the built site is fetched
- **THEN** its head carries `og:title` and `og:description` with that page's title and description, `og:url`
  `https://bundlemcp.dev/guide/quickstart`, `og:image` `https://bundlemcp.dev/og-image.png` with width 1200 and
  height 630, and `twitter:card` `summary_large_image`

#### Scenario: The home page uses the site address
- **WHEN** the home page of the built site is fetched
- **THEN** its `og:url` is `https://bundlemcp.dev/`

#### Scenario: The image has the size it announces
- **WHEN** `docs/public/og-image.png` is read
- **THEN** it is a PNG of exactly 1200×630 pixels
