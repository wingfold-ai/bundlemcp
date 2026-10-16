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
`default`-profile endpoint — a fresh install is never empty and the quickstart has something to click.

#### Scenario: Fresh install is not empty
- **WHEN** the compose stack starts against an empty database
- **THEN** the `echo` server, the `demo` bundle and the `default`-profile `demo` endpoint exist without any manual step

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
(`.github/workflows/publish-docs.yml`); the upload is incremental and never deletes files it did not upload. The
hosting plan has a 10 MB quota, so the built site must stay under 9 MiB; CI checks this on every pull request and again
before each upload. `docs/public/.htaccess` redirects to HTTPS and maps clean URLs to their `.html` files. The published
build alone loads cookieless Plausible analytics (self-hosted, in Switzerland), enabled by the
`DOCS_PLAUSIBLE_SCRIPT_URL` repository variable; local builds, CI and forks load no tracking script. While the
`DOCS_AUTH_USER` and `DOCS_AUTH_PASSWORD` secrets are set, the published site asks for that username and password
(HTTP Basic, on HTTPS only); removing them makes it public again on the next publish.

#### Scenario: Oversized site fails before upload
- **WHEN** the built site exceeds 9437184 bytes
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
