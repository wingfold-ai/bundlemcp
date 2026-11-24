# documentation Specification

## Purpose

What people read to run, use and change bundlemcp. The user-facing documentation site (self-hosting, managing,
connecting clients, integrating), the repository README and the demo seed that makes a fresh install useful. It also
owns the architecture documentation: arc42 sections, append-only ADRs, the LikeC4 model as the single source of
diagrams, and the rule that docs and decisions land in the same pull request as the behaviour they describe.

What the gateway does is specified in the other slices; this slice specifies how it is documented and where.

It merges what were separate specs until 2026-10-13: Docs and onboarding, Architecture documentation.

## Requirements

### Requirement: DOC-1 Repository README
The repository `README.md` MUST cover what bundlemcp is (one screen), a quickstart (clone → `docker compose up` → log in
via the dev IdP → demo bundle works), and links into `docs/` and `openspec/`.

#### Scenario: Quickstart from the README
- **WHEN** a new user follows the README quickstart on a machine with Docker
- **THEN** the compose stack comes up, they can sign in to the admin UI at `http://localhost:3000` through the dev
  identity provider, and a `tools/list` call against the seeded `demo` endpoint with the dev service key returns the
  echo tools

### Requirement: DOC-2 Documentation site
`docs/` MUST be a VitePress site (`docs/.vitepress/`, built with `npm run build` in `docs/`, validated in CI) whose
pages are the operator/integrator guides, grouped by reader task:

- **guide/** — what bundlemcp is, the compose quickstart, core concepts.
- **self-hosting/** — production deployment (public URL, reverse proxy, upgrades, backups — fed by
  [deployment](../deployment/spec.md)), the full `BUNDLEMCP_*` and runtime-config reference, identity provider setup,
  the bootstrap file, day-two operations.
- **manage/** — servers, bundles and tool curation, endpoints, API keys, users and consents, the audit log, export
  and import, the inspector; each page shows the UI path and the equivalent management-API calls.
- **connect/** — **claude.md** (an `oauth_only`-profile endpoint + OAuth walkthrough incl. consent), **chatgpt.md** (the
  `write_as_read` profile + the re-annotation warning, [EP-12](../endpoints/spec.md)), **scripts.md** (API-key access
  for scripts/agents), **stdio-sidecar.md** (wrapping a stdio MCP server in a Streamable-HTTP sidecar with a compose
  snippet — the [UPS-7](../upstreams/spec.md) deliverable).
- **integrate/** — for application layers: the management API, the metering hook, identity forwarding + introspection
  for upstream servers ([protocol](../protocol/spec.md)/[management](../management/spec.md)), and the full
  HTTP surface reference.

Pages document only shipped behaviour. A surface that is reserved but not built is named as such in one place, a "Not
part of this release" section of `docs/self-hosting/operations.md`, rather than described as if it existed; with no
such surface, the section is left out.

#### Scenario: Docs build is a CI gate
- **WHEN** a pull request introduces a dead link in a VitePress page
- **THEN** the CI `docs` job fails at "Build the documentation site"

#### Scenario: Unbuilt surfaces are named, not described
- **WHEN** an operator reads `docs/self-hosting/operations.md`
- **THEN** it describes no page of the admin UI as a placeholder, and names a reserved-but-unbuilt surface only in its
  "Not part of this release" section

### Requirement: DOC-3 Demo seed
The dev compose stack MUST ship a demo bootstrap file ([management](../management/spec.md)), `deploy/seed.yaml`,
registering at least a small example MCP server container (`examples/echo-mcp`), one bundle, and one
`default`-profile endpoint — a fresh install is never empty and the quickstart has something to click. It also
registers the identity demo (`examples/identity-demo-mcp`), which reports what it learns about its caller, in a bundle
and endpoint of its own, so the demo bundle's tools stay those of the quickstart.

#### Scenario: Fresh install is not empty
- **WHEN** the compose stack starts against an empty database
- **THEN** the `echo` server, the `demo` bundle and the `default`-profile `demo` endpoint exist without any manual step

#### Scenario: The identity demo has its own endpoint
- **WHEN** the compose stack starts against an empty database
- **THEN** the `identity-demo` server, the `identity` bundle and the `identity` endpoint exist, and the `demo` bundle
  does not contain `identity-demo`

### Requirement: DOC-4 Diagrams from LikeC4
Docs MUST use the LikeC4-rendered views from `docs/likec4/` ([DOC-9](../documentation/spec.md)) instead
of hand-drawn diagrams: the build compiles the model into a web component (`likec4 codegen webcomponent`) and pages
embed views with the `<LikeC4Diagram view="…" />` component.

#### Scenario: Deployment page embeds the model's view
- **WHEN** the docs site is built
- **THEN** `self-hosting/deploy.md` renders the LikeC4 `production` deployment view and `guide/what-is-bundlemcp.md`
  renders the `index` context view

### Requirement: DOC-5 Docs land with behaviour
Docs MUST be updated in the same PR as the behavior they describe; stale docs are a review blocker, same status as
failing tests.

#### Scenario: Behaviour change without docs
- **GIVEN** a pull request that changes operator-visible behaviour
- **WHEN** it does not update the page that describes that behaviour
- **THEN** the review blocks it as it would a failing test

### Requirement: DOC-6 Published site
Every push to `main` that touches `docs/` MUST build the site and upload it by FTP to Infomaniak web hosting
(`.github/workflows/publish-docs.yml`); the upload is incremental and never deletes files it did not upload. The hosting
plan has a 10 MB quota, so the built site must stay at or under 9.6 MB; CI checks this on every pull request and again
before each upload. `docs/public/.htaccess` redirects to HTTPS and maps clean URLs to their `.html` files. The published
build alone loads cookieless Plausible analytics (self-hosted, in Switzerland), enabled by the
`DOCS_PLAUSIBLE_SCRIPT_URL` repository variable; local builds, CI and forks load no tracking script. While the
`DOCS_AUTH_USER` and `DOCS_AUTH_PASSWORD` secrets are set, the published site asks for that username and password (HTTP
Basic, on HTTPS only); removing them makes it public again on the next publish.

#### Scenario: Oversized site fails before upload
- **WHEN** the built site exceeds 9600000 bytes
- **THEN** the CI `docs` job on the pull request fails, and the publish workflow stops before the FTP upload

#### Scenario: Local build carries no analytics
- **WHEN** the site is built without `DOCS_PLAUSIBLE_SCRIPT_URL` set
- **THEN** no Plausible script tag is emitted

#### Scenario: Password gate follows the secrets
- **GIVEN** `DOCS_AUTH_USER` and `DOCS_AUTH_PASSWORD` are set
- **WHEN** the publish workflow runs
- **THEN** the uploaded `.htaccess` answers HTTPS requests without the matching Basic credentials with `401`

### Requirement: DOC-7 arc42 and OpenSpec
`docs/arc42/` MUST contain the 12 standard arc42 sections as numbered Markdown files (01-introduction-and-goals …
12-glossary). Sections reference specs by requirement ID instead of duplicating normative content; arc42 carries
rationale, views, and cross-cutting concepts. The normative content lives in OpenSpec:
`openspec/specs/<capability>/spec.md` describes what is implemented today, `openspec/changes/<change>/` holds each
change not yet implemented (proposal, delta specs, design, tasks), and `openspec/README.md` is the index. CI runs
`openspec validate --all --strict`, so a malformed spec or change fails the build.

#### Scenario: Twelve arc42 sections
- **WHEN** a contributor lists `docs/arc42/`
- **THEN** it holds `01-introduction-and-goals.md` through `12-glossary.md`, one file per arc42 section

#### Scenario: Malformed spec fails CI
- **WHEN** a pull request adds a requirement under `openspec/specs/` without a `#### Scenario:`
- **THEN** the CI step "Validate OpenSpec specs and changes" fails

### Requirement: DOC-8 ADRs
`docs/adr/` MUST hold Architecture Decision Records in MADR style — `NNNN-title.md` with
**Status / Context / Decision drivers / Decision / Alternatives considered / Consequences** (Consequences split into
Positive and Trade-offs; a section whose content was not recorded at the time says so in one line) — indexed from
arc42 §9 (Architecture Decisions). ADRs are append-only: a later decision MUST NOT edit an earlier record's Context,
Decision or Consequences, only its status line. Two states express the relationship, and both MUST be recorded on the
**earlier** record, because that is the one a reader arrives at: `superseded by NNNN` when the decision is wholly
replaced and MUST NOT be followed, and `accepted` with `Amended by: NNNN` when it was partly revised and both records
still apply. Every `Amends:` MUST have a matching `Amended by:` on each ADR it names, and the arc42 §9 index MUST
agree with the files.

#### Scenario: Missing back-pointer fails CI
- **GIVEN** a new ADR whose status line says `Amends: ADR-0012`
- **WHEN** ADR-0012 carries no `Amended by:` (or `superseded by`) naming it
- **THEN** `python3 tools/check_adr_graph.py` reports the missing back-pointer and the CI `docs` job fails

#### Scenario: Index disagrees with a file
- **WHEN** an ADR's status line and its row in `docs/adr/README.md` or `docs/arc42/09-architecture-decisions.md`
  differ
- **THEN** `tools/check_adr_graph.py` fails, and `--fix` rewrites the index tables from the files

### Requirement: DOC-9 LikeC4
`docs/likec4/` MUST hold the LikeC4 model (`*.c4`): one model of actors/systems/containers and named views for
**context**, **container**, and **deployment**. This model is the *single source* for structural diagrams — arc42 §3
(context), §5 (building blocks), §7 (deployment) and the user docs ([DOC-4](../documentation/spec.md)) embed
these views; no hand-drawn duplicates.

#### Scenario: The three views exist
- **WHEN** the LikeC4 model is parsed
- **THEN** it defines a context view (`index`), a container view (`containers`) and a deployment view (`production`)

### Requirement: DOC-10 Diagram rendering
The LikeC4 CLI (or VS Code extension) renders the views; CI SHALL validate that the model parses
(`npx likec4 validate docs/likec4`) so broken diagrams fail fast.

#### Scenario: Broken model fails CI
- **WHEN** a pull request introduces a syntax error in a `docs/likec4/*.c4` file
- **THEN** the CI step "Validate LikeC4 model" fails

### Requirement: DOC-11 Process
Any change that makes or reverses an architectural decision MUST land with an ADR in the same PR; structural changes
update the LikeC4 model in the same PR. Requirements in `openspec/specs/` and in a change's delta specs link the ADR
where a requirement encodes a decision (e.g. Streamable-HTTP-only →
[ADR-0005](../../../docs/adr/0005-streamable-http-only.md)).

#### Scenario: Architectural change without an ADR
- **GIVEN** a pull request that replaces a technology choice recorded in an ADR
- **WHEN** it adds no ADR recording the new decision
- **THEN** review blocks it until an ADR lands in the same PR

### Requirement: DOC-12 Seed content
`docs/` MUST include arc42 sections filled from the specs, ADRs 0001–0010 covering the decisions taken before the first
commit (rewrite-not-fork; FastMCP v3 — since superseded by [ADR-0030](../../../docs/adr/0030-fastmcp-4.md);
SQLModel/Pydantic-first; Postgres+Redis state split; Streamable-HTTP-only; OIDC-only admin auth; endpoint profiles incl.
ChatGPT re-annotation; full-bidirectional proxy; endpoint-bound tokens + consent; single workspace), and the LikeC4
model with the three views.

#### Scenario: Founding ADRs present
- **WHEN** a contributor lists `docs/adr/`
- **THEN** `0001-rewrite-not-fork.md` through `0010-single-workspace.md` are present

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

### Requirement: DOC-14 Repository links follow its visibility
The documentation site MUST link into the source repository only when it is built with the repository declared
public (`DOCS_REPOSITORY_PUBLIC=true`, a repository variable the publish workflow passes to the build). Built
otherwise, the site carries no link into the repository: no GitHub icon, no "Edit this page" link, no home-page
button and no repository line in the footer; a link into the repository in a page or in a requirement's text keeps
its text and loses the link. The home page, the quickstart and the deployment page then say that the source code and
container images are not public yet. CI builds the site with the same setting as the publish workflow and checks the
output against it.

#### Scenario: A private build has no repository links
- **WHEN** the site is built without `DOCS_REPOSITORY_PUBLIC=true`
- **THEN** no built page and no requirement text links to the repository, and the home page, the quickstart and the
  deployment page show the not-public notice

#### Scenario: A public build links to the repository
- **WHEN** the site is built with `DOCS_REPOSITORY_PUBLIC=true`
- **THEN** the GitHub icon, the edit links and the links in pages are present, and no page shows the not-public
  notice

#### Scenario: A repository link in a private build fails CI
- **WHEN** a built page or requirement text links to the repository while the setting is not `true`
- **THEN** the CI `docs` job fails and names the file

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

### Requirement: DOC-16 Public roadmap
The documentation site MUST publish `/roadmap`, linked from its top navigation, as the project's only roadmap. It
draws one line of stations, in order: Now, In progress, Next, Then and Later. Each station holds themes, never dates.
Each Now theme links the docs page that describes it. Below the line, in page text the site search indexes, the page
links the decision log under "What bundlemcp won't do" and names GitHub Discussions (Ideas) under "Have a say".

#### Scenario: The roadmap is in the navigation
- **WHEN** a visitor opens any page of the built site
- **THEN** the top navigation links `/roadmap`, and that page shows the five stations in order, each with at least one
  theme or, for In progress, the empty-state line

#### Scenario: No dates on the roadmap
- **WHEN** the roadmap page is built
- **THEN** no station or theme names a calendar date, month or quarter

#### Scenario: Now themes link their docs
- **WHEN** a visitor clicks a theme of the Now station
- **THEN** it opens the docs page that describes that theme, and the build reports no dead link

#### Scenario: Won't-do and Have-a-say are searchable
- **WHEN** a visitor searches the site for "won't do"
- **THEN** the roadmap page is among the results, and its "What bundlemcp won't do" section links the decision log

#### Scenario: Discussions follow repository visibility
- **WHEN** the site is built without the repository declared public
- **THEN** "Have a say" names GitHub Discussions as plain text, with no link into the repository

### Requirement: DOC-17 In-progress station from open changes
The In progress station MUST be generated when the site is built, from the changes that are not archived in
`openspec/changes/`. Each change shows its name, the first sentence of its proposal's "Why" and how many of its tasks
are checked out of all of them. A change links its proposal only when the site is built with the repository declared
public. With no active change, the station says that nothing is in flight.

#### Scenario: An active change appears
- **GIVEN** `openspec/changes/<change>/` holds a proposal and a task list with 3 of 8 tasks checked
- **WHEN** the site is built
- **THEN** the In progress station shows the change's name, the first sentence of its proposal's "Why" and "3/8"

#### Scenario: An archived change does not appear
- **WHEN** a change is moved to `openspec/changes/archive/` and the site is rebuilt
- **THEN** the In progress station no longer shows it

#### Scenario: Nothing in flight
- **GIVEN** `openspec/changes/` holds no change outside `archive/`
- **WHEN** the site is built
- **THEN** the In progress station says that nothing is in flight

#### Scenario: A private build links no proposal
- **WHEN** the site is built without the repository declared public
- **THEN** each In progress entry is plain text, with no link into the repository

### Requirement: DOC-18 A page for metamcp users
The documentation site MUST publish a guide page, `/guide/coming-from-metamcp`, listed in the Guide section of the
sidebar, for someone who runs metamcp and is deciding whether to move. The page has these parts:

- **How the concepts map:** a table with one row for each metamcp concept: MCP servers, namespaces, tool overrides,
  endpoints, API keys and middleware. Each row names the bundlemcp concept it becomes and says what differs.
- **What bundlemcp leaves out:** every entry of the decision log
  ([openspec/README.md](../../README.md#decision-log--deliberately-dropped-from-metamcp)) that a metamcp user would
  notice. Each one says what to do instead, or that there is no replacement.
- **Moving a setup over:** a manual migration through a bootstrap document, applied at startup or through import, with
  a worked example that takes a small metamcp setup to its bootstrap document. It names the metamcp importer as a
  roadmap theme, not as something that exists.
- **What you gain:** what bundlemcp adds over metamcp, each item linking the docs page that describes it.

The page names the metamcp release it compares against, and links metamcp's own documentation where it describes
metamcp. Like every page, it describes only bundlemcp behaviour that has shipped ([DOC-2](spec.md)). The repository
README's comparison with metamcp, and the roadmap's "What bundlemcp won't do" section ([DOC-16](spec.md)), link it.

#### Scenario: A metamcp user finds the page
- **WHEN** a visitor searches the site for "metamcp"
- **THEN** the page is among the results, and the Guide section of the sidebar lists it

#### Scenario: Every metamcp concept has a counterpart or a reason
- **WHEN** a reader looks up a metamcp concept from the mapping table
- **THEN** the table names the bundlemcp concept it becomes, or the page says why bundlemcp leaves it out and what
  to do instead

#### Scenario: The importer is not described as shipped
- **WHEN** a reader looks for a one-step migration
- **THEN** the page describes the manual migration through a bootstrap document, and names the importer only as a
  roadmap theme, linking the roadmap

#### Scenario: The worked example applies
- **WHEN** the bootstrap document from the page's worked example is applied to a gateway
- **THEN** it creates the upstreams, bundles and endpoints the example describes, with no validation error

#### Scenario: Claims about metamcp are traceable
- **WHEN** a reader checks what the page says about metamcp
- **THEN** the page names the metamcp release it compared against and links metamcp's documentation

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

### Requirement: DOC-20 Every page has its own description
Every page the documentation site publishes MUST declare its own meta description in its frontmatter: one or two
sentences of at most 160 characters that say what the page covers, in the words someone searching for it would use.
No two pages share a description. The home page title names bundlemcp as an MCP gateway.

#### Scenario: A page's search result describes that page
- **WHEN** the built page `/guide/quickstart` is fetched
- **THEN** its `description` and `og:description` are the quickstart's own description, not the site-wide one

#### Scenario: A page without a description fails the tests
- **WHEN** a published page has no `description` in its frontmatter, or one longer than 160 characters
- **THEN** the hermetic test suite fails and names the page

### Requirement: DOC-21 An llms.txt index of the site
The published site MUST serve `/llms.txt` and `/llms-full.txt`, generated by the build. `llms.txt` starts with the
site's name and description, then lists every sidebar page under its sidebar group, in sidebar order, as a link to
its `https://bundlemcp.dev` URL followed by its description. `llms-full.txt` holds the Markdown of the same pages in
the same order, each without frontmatter and headed by its URL.

#### Scenario: An assistant finds every guide page
- **WHEN** `/llms.txt` is fetched from the built site
- **THEN** it holds a `## Guide` section whose first entry is
  `[What is bundlemcp?](https://bundlemcp.dev/guide/what-is-bundlemcp)` followed by that page's description

#### Scenario: The full text follows the same order
- **WHEN** `/llms-full.txt` is fetched from the built site
- **THEN** it holds the Markdown of every page `llms.txt` lists, in the same order, without frontmatter

### Requirement: DOC-22 A blog with an RSS feed
The documentation site MUST publish a blog at `/blog/`, linked as "Blog" in its top navigation, directly before
"Roadmap". A post is a Markdown page `docs/blog/<slug>.md`, published at `/blog/<slug>`, whose frontmatter declares
`title`, `description`, `date` as `YYYY-MM-DD` and `author`, a name the site knows a profile link for; `draft: true`
marks a draft. A post with a field missing, a malformed date or an unknown author fails the build.

- **Index:** `/blog/` lists every published post, newest first, each with its date, its title linking the post, and
  its description. The list is built from the posts themselves. With no published post, the index says so in one
  sentence and lists nothing.
- **Post page:** shows the post's title, its date, an author line with the author's name linking their profile, and a
  link back to `/blog/`. No page of the blog shows the sidebar.
- **Feed:** the build writes an RSS 2.0 feed to `/blog/feed.xml` with one item per published post, newest first, each
  with the post's title, `https://bundlemcp.dev` URL, description, date and author. Every page's head announces the
  feed with `<link rel="alternate" type="application/rss+xml">`.
- **Drafts:** a production build leaves a draft out entirely: no page is built for it, and the index, the feed, the
  sitemap ([DOC-13](spec.md)) and `llms.txt` ([DOC-21](spec.md)) do not name it. The local development server still
  renders it, marked as a draft.
- **Discovery:** a published post is a page of the site like any other. It is in the sitemap, its description
  ([DOC-20](spec.md)) and link preview tags ([DOC-19](spec.md)) are its own, with `og:type` `article` and its
  publication date, and `llms.txt` lists it under a `## Blog` section, newest first, with `llms-full.txt` holding its
  Markdown.

#### Scenario: The index lists a published post
- **GIVEN** a post `docs/blog/hello.md` dated 2026-11-24, not a draft
- **WHEN** the site is built
- **THEN** `/blog/` lists it with that date, its title linking `/blog/hello` and its description, and the post page
  shows the author line and a link back to `/blog/`

#### Scenario: The feed, sitemap and llms.txt name a published post
- **GIVEN** the same post
- **WHEN** the site is built
- **THEN** `/blog/feed.xml` is an RSS 2.0 document with an item linking `https://bundlemcp.dev/blog/hello`, the sitemap
  lists that URL, and `llms.txt` lists it under `## Blog`

#### Scenario: A draft leaves no trace in production
- **GIVEN** the same post with `draft: true`
- **WHEN** the site is built for production
- **THEN** no page `/blog/hello` is built, and neither the index, the feed, the sitemap nor `llms.txt` names it

#### Scenario: An empty blog says so
- **GIVEN** no published post
- **WHEN** `/blog/` is fetched from the built site
- **THEN** it shows one sentence saying there are no posts yet, and the feed holds no item

#### Scenario: Readers find the feed
- **WHEN** any page of the built site is fetched
- **THEN** its head holds `<link rel="alternate" type="application/rss+xml" href="https://bundlemcp.dev/blog/feed.xml">`

#### Scenario: A post without a date fails the build
- **WHEN** a non-draft post has no `date`, or one not of the form `YYYY-MM-DD`
- **THEN** the build fails and names the post

## Out of scope

### Docs and onboarding

- Theming beyond VitePress's default theme. Operators who want the docs elsewhere can host the static output of
  `docs/.vitepress/dist` anywhere.
- Rendering `docs/arc42`, `docs/adr` and `docs/likec4` inside the site — they are contributor material that links into
  `openspec/` and stays on GitHub ([documentation](../documentation/spec.md)).
- i18n of docs (decision log).

### Architecture documentation

- Generated API reference (OpenAPI serves that — [MGMT-3](../management/spec.md)).
- Publishing the arc42 docs as a website (in-repo Markdown for v1).

## Notes

### Docs and onboarding

- The example MCP server for DOC-3 is `examples/echo-mcp`, a three-tool FastMCP server including an annotated write tool
  so the write_as_read profile has something to re-annotate. The seed also registers `examples/oauth-demo-mcp` (a
  per-user OAuth upstream) and `claude`/`chatgpt` endpoints on the same bundle.
- VitePress was chosen over plain Markdown (2026-09) because the guides need navigation, search and a home page to be
  usable by someone who has not read the repo; the Markdown source stays reviewable in PRs, which keeps DOC-5
  enforceable.
