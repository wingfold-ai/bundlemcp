## ADDED Requirements

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
