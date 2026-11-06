# admin-ui Specification

## Purpose

The admin app, and the catalogue signed-in users see. A Nuxt single-page app that is a pure client of the management
API, with types generated from its OpenAPI document: pages for upstreams (with guided registration), bundles and
curation, endpoints and their connection cards, API keys, users and consents, audit, live logs and settings, the
built-in inspector, and a catalogue showing a signed-in non-admin what they can connect to.

Every action the UI offers is specified as API behaviour in the management slice and the feature slices.

## Requirements

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
- **Settings** — runtime `Config` editing: each key can be saved or reset to its default; export and import of the
  configuration ([MGMT-22](../management/spec.md)).
- **Live logs** — the live tail of every replica's recent events, with filters and pause/resume
  ([OPS-15](../operations/spec.md)).
- **Inspector** — connect to a registered upstream, an endpoint of this gateway or an ad-hoc URL, see what it offers
  and call its tools (UI-8..UI-11).

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

### Requirement: UI-8 Inspector targets
The inspector SHALL connect to three kinds of target: (a) any registered upstream server, using its stored
configuration — static headers and upstream OAuth applied server-side, secrets never sent to the browser; (b) any
endpoint of this gateway, exercising the full public path (authentication, profile, curation, metering); (c) an
arbitrary URL with headers entered ad hoc.

#### Scenario: A registered upstream uses its stored credentials
- **GIVEN** upstream `weather` registered with a static `Authorization` header
- **WHEN** an admin inspects `weather`
- **THEN** the upstream receives the stored header, and no response to the browser contains its value

#### Scenario: An endpoint is inspected through its public path
- **GIVEN** endpoint `b1-chatgpt` with the `write_as_read` profile and a disabled tool in its bundle
- **WHEN** an admin lists tools of `b1-chatgpt` in the inspector with a valid credential for it
- **THEN** the list matches what a client of that endpoint sees: curated, profile-annotated, without the disabled tool

#### Scenario: An ad-hoc URL is inspected with the entered headers
- **WHEN** an admin enters a URL and a header and connects
- **THEN** the gateway connects to that URL with that header and stores neither

### Requirement: UI-9 Inspector operations
The inspector SHALL support `initialize` with the target's capabilities shown, `ping`, `tools/list` with each tool's
schema, and `tools/call` with a form generated from the tool's input schema and a raw-JSON fallback. It SHALL show the
response or error, progress notifications received during a call, and the time each request took.

#### Scenario: Capabilities are shown after initialize
- **WHEN** an admin connects to a target
- **THEN** the UI shows the server's name, version, negotiated protocol revision and advertised capabilities

#### Scenario: A call is built from the input schema
- **GIVEN** a tool whose input schema has a required string `city`
- **WHEN** the admin opens the tool
- **THEN** a form with a required `city` field is shown, and switching to raw JSON shows the same arguments

#### Scenario: Progress and timing are shown
- **WHEN** a called tool sends two progress notifications before its result
- **THEN** the UI shows both progress notifications as they arrive, then the result and the request's duration

#### Scenario: An error result is displayed
- **WHEN** a call returns a JSON-RPC error or a result with `isError: true`
- **THEN** the UI shows the error content rather than an empty result

### Requirement: UI-10 Traffic is proxied by the management API
The browser MUST never talk to an inspector target directly: the management API proxies inspector traffic,
authenticated like every management route ([MGMT-2](../management/spec.md)), so stored secrets stay
server-side and no target needs CORS. Ad-hoc URL targets MUST pass the egress policy
([SEC-1, SEC-2](../security/spec.md)).

#### Scenario: Inspector requests need management credentials
- **WHEN** an inspector route is called without an admin session or service API key
- **THEN** it is refused as unauthenticated and no target is contacted

#### Scenario: A blocked ad-hoc URL is refused
- **WHEN** an admin inspects an ad-hoc URL that resolves to a blocked range
- **THEN** no request is sent to it and the inspector reports `egress_denied`

### Requirement: UI-11 Inspector calls are attributed
Inspector calls against **endpoints** SHALL go through the real public path and be audited like any client call
([OPS-1](../operations/spec.md)). Calls against upstreams and ad-hoc URLs bypass the endpoint context:
they MUST be marked `source=inspector` in the logs and MUST NOT create audit records.

#### Scenario: An endpoint call is audited
- **WHEN** an admin calls a tool through an endpoint in the inspector
- **THEN** one audit record is written for it, as for any client of that endpoint

#### Scenario: An upstream call is logged, not audited
- **WHEN** an admin calls a tool on upstream `weather` directly in the inspector
- **THEN** the call's log events carry `source=inspector` and no audit record is written

### Requirement: UI-12 Errors shown where they happened
On a detail page made of several cards, an action that fails SHALL show its error on the card whose action failed,
whether the client-side validation or the API refused it, and nowhere else on the page. Starting another action on a
card SHALL clear only that card's error. A failure to load the page's own data SHALL still be shown at the top of the
page.

#### Scenario: A curation error stays on the curation card
- **GIVEN** a bundle with a member tool
- **WHEN** the admin enters an annotation override that is not a JSON object and saves that tool's row
- **THEN** the tool curation card shows the error, and the page top and every other card show none

#### Scenario: An API refusal is shown on the card that sent it
- **GIVEN** upstream `echo` is a member of a bundle
- **WHEN** the admin renames it without acknowledging the consequence and the API refuses the rename
- **THEN** the refusal is shown on the card holding the rename control, and the configuration card shows no error

#### Scenario: Errors on two cards are independent
- **GIVEN** the members card of a bundle shows an error from a failed member change
- **WHEN** the admin saves the bundle's description successfully
- **THEN** the members card still shows its error, and the meta card shows none

#### Scenario: A failed load is shown at the page top
- **GIVEN** the gateway fails to return a bundle's tools
- **WHEN** the admin opens the bundle's detail page
- **THEN** the load error is shown at the top of the page

### Requirement: UI-13 Admin UI verified in CI
CI SHALL run every browser scenario of the admin UI against the development stack for every pull request, and SHALL
run unit tests for the UI's pure logic: name validation, the tool-argument form, the prompt preview and the
invalidation of the query cache. A failing scenario or unit test SHALL fail the run. No scenario is excluded from the
run, by a marker or otherwise.

#### Scenario: A broken page fails CI
- **GIVEN** a change that breaks adding a member on the bundle detail page
- **WHEN** CI runs for the pull request
- **THEN** the integration job fails on the browser scenario that adds a member

#### Scenario: A broken validation rule fails CI
- **GIVEN** a change that lets the name validation accept `my__server` as an upstream name
- **WHEN** CI runs for the pull request
- **THEN** the frontend job fails on the unit test for upstream names

#### Scenario: A new browser scenario runs without a CI edit
- **WHEN** a contributor adds a browser scenario
- **THEN** the next CI run executes it without any change to the workflow

### Requirement: UI-14 Unsaved edits survive a refresh
A form field or table row the admin has changed and not yet saved SHALL keep the admin's value when the data behind it
is read from the gateway again, whatever caused the read: another card's action, a save elsewhere on the page or a
background refetch. A field the admin has not changed SHALL take the gateway's new value. Once a save succeeds and the
gateway reports the saved value, the field counts as unchanged again.

#### Scenario: A refetch does not undo typing
- **GIVEN** the admin has typed a new description into a bundle's meta card and not saved it
- **WHEN** another card's action on the same page makes the bundle be read again
- **THEN** the description field still shows what the admin typed, and saving sends that value

#### Scenario: Untouched fields follow the gateway
- **GIVEN** the admin has changed a bundle's description but not its catalogue overview
- **WHEN** the bundle is read again and its overview was changed elsewhere meanwhile
- **THEN** the overview field shows the new overview and the description field keeps the admin's edit

#### Scenario: A saved field follows the gateway again
- **GIVEN** the admin saved a new description and the gateway reports it
- **WHEN** the description is later changed elsewhere and the bundle is read again
- **THEN** the description field shows the newer value

## Out of scope

- i18n (decision log), mobile-optimized layouts, theming beyond the brand tokens (the wordmark teal as the primary
  colour, the documentation site's gray surfaces, the logo in the header and as favicon) applied through Nuxt UI's
  design tokens — no per-component styling.
