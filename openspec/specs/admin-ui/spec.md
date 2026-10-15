# admin-ui Specification

## Purpose

The admin app, and the catalogue signed-in users see. A Nuxt single-page app that is a pure client of the management
API, with types generated from its OpenAPI document: pages for upstreams (with guided registration), bundles and
curation, endpoints and their connection cards, API keys, users and consents, audit and settings, and a catalogue
showing a signed-in non-admin what they can connect to. The built-in inspector will live here once built.

Every action the UI offers is specified as API behaviour in the management slice and the feature slices.

## Requirements

### Requirement: UI-1 Pages
The admin UI SHALL provide these pages:

- **Upstream servers** — list with health and connection-state badges and the MCP revision negotiated at the last
  successful probe ([UPS-10](../upstreams/spec.md)); detail: config, secret header editing (write-only — an
  empty field keeps the stored values), forward-headers, upstream OAuth connect status
  ([UPS-29](../upstreams/spec.md)), discovered tools with their last-seen time, and a *Refresh tools* action that
  re-probes the server and reports the discovered and changed counts or the connection state it ran into.
- **Bundles** — list; detail: member servers (add/remove/enable), tool curation table (enable toggles, inline
  name/title overrides, *overridden* and *member disabled* badges — [BND-16](../bundles/spec.md)), the bundle's
  own prompts and resources ([bundles](../bundles/spec.md)), endpoints of this
  bundle, and the catalogue overview shown to users ([BND-11](../bundles/spec.md)).
- **Catalogue** — what a signed-in non-admin sees: the bundles they can connect to, each with its overview and the
  tools it serves ([BND-11](../bundles/spec.md)), and per endpoint the copy-paste URL and setup steps for the client its
  profile is recommended for.
- **Composition** — one grid of bundles against registered servers, marking each membership and whether it is enabled
  ([BND-4](../bundles/spec.md)). It answers what spans bundles: which bundles a server is used by, and which servers are
  registered but in no bundle, so unreachable through any endpoint.
- **Endpoints** — list; detail: bundle, profile (with the write_as_read warning
  [EP-12](../endpoints/spec.md)),
  auth modes, rate limits, connection card (copy-paste URL + per-client setup instructions —
  [EP-7](../endpoints/spec.md)).
- **API keys** — create (one-time value display), kind, active/inactive state, deactivate and delete
  ([auth](../auth/spec.md)).
- **Audit** — filterable table (endpoint, status, tool, time range) + CSV download ([OPS-6](../operations/spec.md)).
- **Users** — list of provisioned users, admin flag display, deactivate action ([AUTH-20](../auth/spec.md)),
  per-user OAuth consents with revoke ([AUTH-11](../auth/spec.md)).
- **Settings** — runtime `Config` editing: each key can be saved or reset to its default.

The navigation also carries *Live logs* and *Inspector* entries; both pages are placeholders that state their backend is
not implemented ([add-live-logs](../../changes/add-live-logs/proposal.md),
[add-inspector](../../changes/add-inspector/proposal.md)).

#### Scenario: Navigation reaches every page
- **GIVEN** a signed-in admin
- **WHEN** they follow each navigation entry
- **THEN** each page renders, including the Composition grid at `/bundles/matrix`

#### Scenario: Server list shows health, connection state and protocol
- **GIVEN** the seeded `echo` server has been probed successfully
- **WHEN** the admin opens *Upstream servers*
- **THEN** its row shows a health badge, a connection-state badge and the negotiated MCP revision

#### Scenario: Composition grid finds orphan servers
- **GIVEN** a registered server that belongs to no bundle
- **WHEN** the admin opens the Composition page
- **THEN** the grid marks no membership for it and the page lists it as registered but in no bundle

#### Scenario: API key value shown once
- **WHEN** the admin creates an API key
- **THEN** the full key value is displayed once with a copy button, and the list afterwards shows only its name, kind
  and state

#### Scenario: Revoking a user's consent
- **GIVEN** a user with an OAuth consent
- **WHEN** the admin expands that user's consents on the Users page and revokes one
- **THEN** the consent is removed from the list

### Requirement: UI-2 Auth
Every route of the admin UI MUST require a signed-in user: an anonymous visitor is redirected to the gateway's OIDC
login ([auth](../auth/spec.md)) and returned to the page they asked for, and a session that expires
mid-visit sends the browser back through login on the next `401`. A signed-in user without admin rights SHALL only
reach the catalogue: any management page redirects them to `/catalogue`, and no management navigation is shown.

#### Scenario: Anonymous visitor is sent to login
- **WHEN** a visitor without a session opens `/bundles`
- **THEN** the browser is redirected to the gateway's `/login` with a `next` parameter pointing back at `/bundles`

#### Scenario: Non-admin is kept on the catalogue
- **GIVEN** a person without admin rights signed in through the identity provider
- **WHEN** they try to open a management page
- **THEN** they are sent back to the catalogue

### Requirement: UI-3 Frontend API layer
The UI MUST call the management API only through a client typed from the generated `/api/v1/openapi.json`
(`apps/web/openapi.json` → `apps/web/types/api.d.ts`, via `openapi-fetch`); no DTO type is hand-written. CI regenerates
both files and fails when they differ from the committed ones. Pages load data through this client (with Nuxt's
`useAsyncData` where a page is rendered from one query) and reload the affected data after each mutation.

#### Scenario: Stale generated contract fails CI
- **GIVEN** a change to a `schemas/` DTO without re-running `npm run openapi`
- **WHEN** CI runs the frontend job
- **THEN** the "Generated API contract is current" step fails on the diff of `openapi.json` / `types/api.d.ts`

### Requirement: UI-4 Form validation
Forms SHALL check the backend's naming rules before submitting, so users see the error without a round trip: names
must match `^[a-zA-Z0-9_-]+$`, server names must not contain `__`, endpoint names must not be reserved, an endpoint
needs at least one auth mode and `none` cannot be combined with another mode or used without allowing unauthenticated
access, and bundle prompt and resource names follow their own patterns. Errors the client cannot know in advance (such
as a name already taken) are shown from the API's response.

#### Scenario: Double underscore in a server name is blocked client-side
- **WHEN** the admin submits a new server named `my__server`
- **THEN** the form shows `Server name must not contain "__"` and no request is sent

#### Scenario: Reserved endpoint name is blocked client-side
- **WHEN** the admin creates an endpoint named `api`
- **THEN** the form shows that the name is reserved and no request is sent

### Requirement: UI-5 Web container is optional
The web container MUST be optional at runtime: the gateway is fully operable via the management API alone
([management](../management/spec.md)); the UI holds no state of its own and talks to `/api/v1` with the admin
session cookie.

#### Scenario: Gateway operated without the web app
- **GIVEN** a deployment running the gateway without the `web` service
- **WHEN** an operator registers a server, creates a bundle and an endpoint with a service API key
- **THEN** the endpoint serves the bundle exactly as if the steps had been done in the UI

### Requirement: UI-6 Guided server registration
Registering a server SHALL start from its URL (or a pasted registry `server.json`,
[UPS-15](../upstreams/spec.md)): the UI runs inspection ([UPS-11](../upstreams/spec.md)), shows what
was detected, and asks only what the upstream cannot answer, as one question — *where does the credential come from?*
— with the detected answer pre-selected: none; a key or token the operator enters (which the operator can verify by
re-inspecting with it before saving); each user signs in with their own account; one shared account (interactive, or
client credentials, [UPS-35](../upstreams/spec.md)); a delegated gateway token
([AUTH-32](../auth/spec.md)). OAuth client fields appear only when inspection reports that no automatic
client identification is possible (and always for client credentials). Forward headers, the identity header and the
protocol pin sit in a collapsed *Advanced* section. The server detail page shows the connection state (UPS-12) and
offers the fix for a state that contradicts the configuration, and shows the upstream OAuth card only for OAuth servers.

#### Scenario: Open server pre-selects no credential
- **GIVEN** an upstream that answers without authentication
- **WHEN** the admin enters its URL and checks it
- **THEN** the form shows what was detected and pre-selects "No credential needed"

#### Scenario: OAuth server pre-selects per-user sign-in
- **GIVEN** an upstream that answers `401` with OAuth protected-resource metadata
- **WHEN** the admin checks its URL
- **THEN** "Each user signs in with their own account" is pre-selected, and client id fields appear only if inspection
  reports that a pre-registered client is required

#### Scenario: Detail page offers the fix for a contradicting state
- **GIVEN** a server configured without credentials whose last probe found it requires OAuth
- **WHEN** the admin opens its detail page
- **THEN** the connection state is shown with a "Switch to OAuth" action

### Requirement: UI-7 Upstream server naming
Navigation and the list page's title SHALL say *Upstream servers* ([UPS-16](../upstreams/spec.md)). The pages
live at `/upstreams` and `/upstreams/{name}`.

#### Scenario: Upstream pages and navigation
- **WHEN** a signed-in admin opens the admin UI
- **THEN** the navigation entry reads *Upstream servers* and links to `/upstreams`, and a server's detail page is at
  `/upstreams/{name}`

## Out of scope

- i18n (decision log), mobile-optimized layouts, theming beyond the brand tokens (the wordmark teal as the primary
  colour, the documentation site's gray surfaces, the logo in the header and as favicon) applied through Nuxt UI's
  design tokens — no per-component styling.
