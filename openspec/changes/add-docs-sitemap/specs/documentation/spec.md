# Spec Delta

## ADDED Requirements

### Requirement: DOC-13 Search-engine discovery
The published documentation site MUST serve `/sitemap.xml` and `/robots.txt`. The sitemap lists the canonical URL
of every page the site publishes, as `https://bundlemcp.com` followed by the page's clean path, and no URL for the
not-found page or for material the site excludes. `robots.txt` allows every crawler and names
`https://bundlemcp.com/sitemap.xml`. Each page's last-modified date, on the page and in the sitemap, is the date of
the last commit that changed that page, not the date of the build. While the site asks for a password
([DOC-6](spec.md)), both files ask for it too.

#### Scenario: Every page is in the sitemap
- **WHEN** the site is built
- **THEN** the sitemap holds exactly one `https://bundlemcp.com` URL per built page, without an `.html` suffix, and
  none for the not-found page

#### Scenario: A page missing from the sitemap fails CI
- **WHEN** a built page has no entry in the built sitemap, or the sitemap lists a URL with no built page
- **THEN** the CI `docs` job fails and names the page

#### Scenario: Crawlers find the sitemap
- **WHEN** a crawler fetches `/robots.txt` from the public site
- **THEN** it is allowed to crawl every path and finds `Sitemap: https://bundlemcp.com/sitemap.xml`

#### Scenario: Dates come from page history
- **WHEN** the publish workflow builds the site
- **THEN** a page untouched since an earlier commit carries that commit's date, not the date of the push being
  published
