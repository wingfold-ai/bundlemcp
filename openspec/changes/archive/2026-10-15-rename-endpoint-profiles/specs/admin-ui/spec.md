## MODIFIED Requirements

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
