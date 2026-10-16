## MODIFIED Requirements

### Requirement: UI-1 Pages
The admin UI SHALL provide these pages:

- **Upstream servers** — list with health and connection-state badges and the MCP revision negotiated at the last
  successful probe ([UPS-10](../upstreams/spec.md)); detail: config, secret header editing
  (write-only — an empty field keeps the stored values), forward-headers, upstream OAuth connect status
  ([UPS-29](../upstreams/spec.md)), discovered tools with their last-seen time and a *stale* badge on
  each tool the last discovery no longer found, a *Refresh tools* action that re-probes the server and reports the
  discovered and changed counts or the connection state it ran into, and a *Refresh & prune* action that additionally
  removes the stale tools ([UPS-19](../upstreams/spec.md)).
- **Bundles** — list; detail: member servers (add/remove/enable), tool curation table (enable toggles, inline
  name, title, description and annotation overrides, *stale*, *overridden* and *member disabled* badges —
  [BND-16](../bundles/spec.md)), the bundle's own prompts and resources
  ([bundles](../bundles/spec.md)), endpoints of this bundle, and the
  catalogue overview shown to users ([BND-11](../bundles/spec.md)).
- **Catalogue** — what a signed-in non-admin sees: the bundles they can connect to, each with its overview and the
  tools it serves ([BND-11](../bundles/spec.md)), and per endpoint the copy-paste URL and setup steps for the client its
  profile is recommended for.
- **Composition** — one grid of bundles against registered servers, marking each membership and whether it is enabled
  ([BND-4](../bundles/spec.md)). It answers what spans bundles: which bundles a server is used by, and
  which servers are registered but in no bundle, so unreachable through any endpoint.
- **Endpoints** — list; detail: bundle, profile (with write_as_read-profile warning
  [EP-12](../endpoints/spec.md)), auth modes, rate limits, connection card (copy-paste URL +
  per-client setup instructions — [EP-7](../endpoints/spec.md)).
- **API keys** — create (one-time value display) with a kind and, for an endpoint-kind key, an endpoint-scope picker
  (no endpoint selected = every endpoint); the list shows each key's kind, scope and active/inactive state, with
  deactivate, re-activate and delete actions ([auth](../auth/spec.md)).
- **Audit** — filterable table (time range, endpoint, bundle, upstream server, tool, caller and status) + CSV download
  of the whole filtered result, not only the loaded page ([OPS-6](../operations/spec.md)).
- **Users** — list of provisioned users, admin flag display, deactivate action
  ([AUTH-20](../auth/spec.md)), per-user OAuth consents with revoke
  ([AUTH-11](../auth/spec.md)).
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
- **THEN** the full key value is displayed once with a copy button, and the list afterwards shows only its name, kind,
  scope and state

#### Scenario: Endpoint key scoped from the UI
- **GIVEN** endpoints `a` and `b`
- **WHEN** the admin creates an endpoint-kind key and selects only endpoint `a` in the scope picker
- **THEN** the created key lists `a` as its scope, and the key is not accepted at endpoint `b`

#### Scenario: Inactive key re-activated
- **GIVEN** a deactivated API key
- **WHEN** the admin clicks *Re-activate* on its row
- **THEN** the row shows the key as active and the next request with that key is authenticated on every replica

#### Scenario: Stale tool pruned from the detail page
- **GIVEN** an upstream whose last discovery no longer found tool `old_tool`
- **WHEN** the admin opens the upstream's detail page
- **THEN** `old_tool` carries a *stale* badge, and after *Refresh & prune* it is no longer listed

#### Scenario: Audit CSV covers the filtered result
- **GIVEN** more audit records match the active filters than the page has loaded
- **WHEN** the admin downloads the CSV
- **THEN** the file holds every matching record, with the caller columns

#### Scenario: Revoking a user's consent
- **GIVEN** a user with an OAuth consent
- **WHEN** the admin expands that user's consents on the Users page and revokes one
- **THEN** the consent is removed from the list

### Requirement: UI-3 Frontend API layer
The UI MUST call the management API only through a client typed from the generated `/api/v1/openapi.json`
(`apps/web/openapi.json` → `apps/web/types/api.d.ts`, via `openapi-fetch`); no DTO type is hand-written. CI regenerates
both files and fails when they differ from the committed ones. Pages SHALL read data through a caching query layer: each
query result is cached under a key derived from the resource and its parameters, a page revisited within the session
renders the cached result while it refetches, and each mutation invalidates every cached query whose data it changes,
so every view of that data refreshes without a page reloading it by hand.

#### Scenario: Stale generated contract fails CI
- **GIVEN** a change to a `schemas/` DTO without re-running `npm run openapi`
- **WHEN** CI runs the frontend job
- **THEN** the "Generated API contract is current" step fails on the diff of `openapi.json` / `types/api.d.ts`

#### Scenario: A mutation refreshes other views of the data
- **GIVEN** the admin has visited the Composition grid
- **WHEN** they create a bundle on the Bundles page and then return to the Composition grid
- **THEN** the grid shows the new bundle without a manual reload

#### Scenario: Revisited page renders from the cache
- **GIVEN** the admin has loaded the Upstream servers list
- **WHEN** they open a server's detail page and navigate back
- **THEN** the list renders immediately from the cache and is refetched in the background

### Requirement: UI-4 Form validation
Forms SHALL check the backend's naming rules before submitting, so users see the error without a round trip. The
rules SHALL be generated from the constraints the OpenAPI document publishes, never hand-copied: names must match
`^[a-zA-Z0-9_-]+$`, upstream names must not contain `__`, endpoint names must not be reserved, an endpoint needs at
least one auth mode and `none` cannot be combined with another mode or used without allowing unauthenticated access,
and bundle prompt and resource names follow their own patterns. A name already taken by an existing resource of the
same kind SHALL be reported before submitting; conflicts the client cannot know in advance (a concurrent create) are
shown from the API's response.

#### Scenario: Double underscore in a server name is blocked client-side
- **WHEN** the admin submits a new upstream named `my__server`
- **THEN** the form shows `Upstream name must not contain "__"` and no request is sent

#### Scenario: Reserved endpoint name is blocked client-side
- **WHEN** the admin creates an endpoint named `api`
- **THEN** the form shows that the name is reserved and no request is sent

#### Scenario: Taken name is reported before submitting
- **GIVEN** a bundle named `demo` exists
- **WHEN** the admin types `demo` as the name of a new bundle
- **THEN** the form shows that the name is taken and the create request is not sent

#### Scenario: Validation follows the published schema
- **GIVEN** a backend naming constraint changes and `npm run openapi` is re-run
- **WHEN** the web app is built
- **THEN** the form validation applies the new constraint without a hand edit to the frontend rules

### Requirement: UI-7 Upstream server naming
Navigation, the list page's title and the detail page's title SHALL say *Upstream servers* / *Upstream server*
([UPS-16](../upstreams/spec.md)); buttons, empty states, tooltips and error copy MAY use the
short *upstream*, never a bare *server*. The pages live at `/upstreams` and `/upstreams/{name}`.

#### Scenario: Upstream pages and navigation
- **WHEN** a signed-in admin opens the admin UI
- **THEN** the navigation entry reads *Upstream servers* and links to `/upstreams`, and a server's detail page is at
  `/upstreams/{name}`

#### Scenario: Detail page title
- **WHEN** the admin opens `/upstreams/echo`
- **THEN** the page title reads *Upstream server: echo*

#### Scenario: Error copy says upstream
- **WHEN** a form on the upstream pages rejects a name
- **THEN** the message names an *upstream*, not a *server*
