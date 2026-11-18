# Spec Delta

## ADDED Requirements

### Requirement: DOC-15 One canonical address
The documentation site's address MUST be `https://bundlemcp.dev`. Every other host name the hosting serves for it
(`bundlemcp.com`, `www.bundlemcp.com`, `www.bundlemcp.dev`) answers every request with a permanent redirect (`301`)
to the same path and query on `https://bundlemcp.dev`, in one hop also from plain HTTP. The published build reports
page views to Plausible under `bundlemcp.dev`.

#### Scenario: An old address keeps its path
- **WHEN** a client requests `https://bundlemcp.com/guide/quickstart?x=1`
- **THEN** the answer is `301` with `Location: https://bundlemcp.dev/guide/quickstart?x=1`

#### Scenario: Plain HTTP on an old address takes one hop
- **WHEN** a client requests `http://www.bundlemcp.com/`
- **THEN** the answer is `301` with `Location: https://bundlemcp.dev/`

#### Scenario: The canonical address serves the site
- **WHEN** a client requests `https://bundlemcp.dev/guide/quickstart`
- **THEN** the page is served with `200`, and `http://bundlemcp.dev/` redirects to `https://bundlemcp.dev/`

## MODIFIED Requirements

### Requirement: DOC-13 Search-engine discovery
The published documentation site MUST serve `/sitemap.xml` and `/robots.txt`. The sitemap lists the canonical URL
of every page the site publishes, as `https://bundlemcp.dev` followed by the page's clean path, and no URL for the
not-found page or for material the site excludes. `robots.txt` allows every crawler and names
`https://bundlemcp.dev/sitemap.xml`. Each page's last-modified date, on the page and in the sitemap, is the date of
the last commit that changed that page, not the date of the build. While the site asks for a password
([DOC-6](spec.md)), both files ask for it too.

#### Scenario: Every page is in the sitemap
- **WHEN** the site is built
- **THEN** the sitemap holds exactly one `https://bundlemcp.dev` URL per built page, without an `.html` suffix, and
  none for the not-found page

#### Scenario: A page missing from the sitemap fails CI
- **WHEN** a built page has no entry in the built sitemap, or the sitemap lists a URL with no built page
- **THEN** the CI `docs` job fails and names the page

#### Scenario: Crawlers find the sitemap
- **WHEN** a crawler fetches `/robots.txt` from the public site
- **THEN** it is allowed to crawl every path and finds `Sitemap: https://bundlemcp.dev/sitemap.xml`

#### Scenario: Dates come from page history
- **WHEN** the publish workflow builds the site
- **THEN** a page untouched since an earlier commit carries that commit's date, not the date of the push being
  published
