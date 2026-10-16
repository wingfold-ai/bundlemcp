# upstreams Specification

## Purpose

The upstream MCP servers the gateway proxies, and how it reaches them. Registering an upstream server (Streamable HTTP
only, with inspection that pre-fills a registration), its connection settings and health, the egress policy every
request to it passes, and discovering and caching its tools in Postgres so bundles can be curated while it is down. It
also covers authenticating to upstreams: static headers, OAuth with tokens held per user or shared, the interactive
connect flow, refresh on 401, and introspection for forwarded bearers.

How an upstream's tools are presented in a bundle is the bundles slice; the caller's identity forwarded to an upstream
is the auth slice.

It merges what were separate specs until 2026-10-13: Upstream registry, Tool discovery, Upstream OAuth.

## Requirements

### Requirement: UPS-1 Server fields
A server MUST have: unique slug-safe `name` (doubles as the tool prefix), optional `description`, `url` (http/https),
`static_headers`, `forward_headers`, `auth_mode` (`none` | `static_headers` | `upstream_oauth` | `delegated_token`), a
`connection_state` (UPS-12), and a `capabilities` snapshot captured at discovery ([UPS-22](../upstreams/spec.md))
that feeds capability aggregation ([PROT-11](../protocol/spec.md)). See
[architecture](../architecture/spec.md). `none` and `static_headers` differ only in whether static headers are stored,
so the gateway derives one from the other on every write: a server that is neither `upstream_oauth` nor
`delegated_token` is `static_headers` exactly when it holds at least one static header.

#### Scenario: Auth mode follows the stored headers
- **WHEN** a server is written with `auth_mode: none` and one static header
- **THEN** it is stored and returned with `auth_mode: static_headers`

#### Scenario: Removing the last static header settles on none
- **WHEN** a `static_headers` server is updated with an empty `static_headers` map
- **THEN** it is stored with `auth_mode: none`

#### Scenario: OAuth and delegated modes are kept as written
- **WHEN** a server is written with `auth_mode: upstream_oauth` or `delegated_token`
- **THEN** the mode is stored unchanged regardless of static headers

### Requirement: UPS-2 Management and probe on write
Create/update/delete/list/get MUST be available in the management API ([management](../management/spec.md))
and the UI. Create and update MUST validate the config by connecting to the upstream (protocol negotiation per UPS-10)
and running `tools/list`, storing discovered tools on success ([upstreams](../upstreams/spec.md)). The probe
runs in the background after the write has committed, so the write returns before it completes. A failed probe stores
the server with its failure recorded (explicitly allowed: registering a server that isn't up yet), never blocks
creation from the API. An update probes only when it changes what discovery depends on — `url`, `static_headers`,
`forward_headers`, `auth_mode`, `identity_mode`, `send_identity_header` or `protocol_mode` — or when the server's last
probe did not succeed (`connection_state` other than `ready`). Re-applying an unchanged config to a working server is a
database write only, so an upstream that scales to zero stays idle across deploys that re-apply every server
([ADR-0043](../../../docs/adr/0043-contact-upstreams-only-with-a-reason.md)). Explicit refresh and inspection (UPS-11)
always contact the upstream.

#### Scenario: Creating a server that is down still succeeds
- **WHEN** `PUT /api/v1/upstreams/{name}` creates a server whose URL does not answer
- **THEN** the response is `200` with the stored server, and the background probe later records the failure in
  `connection_state`

#### Scenario: Unchanged re-apply does not contact the upstream
- **WHEN** a server whose `connection_state` is `ready` is upserted with exactly its stored configuration
- **THEN** no probe is scheduled and the upstream receives no request

#### Scenario: Changing the URL re-probes
- **WHEN** a `ready` server is upserted with a different `url`
- **THEN** a probe of the new URL is scheduled

### Requirement: UPS-3 Static headers are write-only
`static_headers` values are secrets: write-only in the API (responses MUST return key names only), never logged
([ARC-18](../architecture/spec.md)).

#### Scenario: Responses list header names only
- **WHEN** a server with static header `Authorization: Bearer s3cret` is read through the API
- **THEN** the response carries `static_header_names: ["Authorization"]` and no header value

### Requirement: UPS-4 Health status
`health_status` + `last_error` MUST be maintained: set to `error` with a message after `N` consecutive connection
failures, reset to `ok` on the next successful connect — metamcp's error tracker semantics, minus the process
babysitting. `N` is the runtime config key `server_error_attempts` (default 3), read when a failure is counted, so a
change applies without a restart. Both discovery probes and live upstream calls count: a call counts as a failure when
the upstream could not be reached or answered without a valid MCP response, and as a success when it got any MCP
response, including a tool error. A refused credential, a call timeout and a cancellation count as neither. The
consecutive-failure count is shared by every replica, so failures seen on different replicas add up.

#### Scenario: Three failed probes mark the server as failing
- **WHEN** discovery fails three times in a row for a server
- **THEN** the server's `health_status` is `error` and `last_error` carries the last failure's message

#### Scenario: A success heals the server
- **WHEN** a server with `health_status: error` is probed successfully
- **THEN** `health_status` becomes `ok` and `last_error` is cleared

#### Scenario: The threshold is runtime-configurable
- **GIVEN** `server_error_attempts` is set to `5` through the config API
- **WHEN** discovery fails four times in a row for a server
- **THEN** its `health_status` is not `error`, and it becomes `error` on the fifth consecutive failure

#### Scenario: Failures on different replicas add up
- **WHEN** two consecutive probes of a server fail on replica A and the third fails on replica B
- **THEN** the server's `health_status` is `error`

#### Scenario: Live call failures count
- **GIVEN** `server_error_attempts` is `3` and a member upstream that stopped accepting connections
- **WHEN** three `tools/call` requests to its tools fail because the upstream cannot be reached
- **THEN** the server's `health_status` is `error`

#### Scenario: A tool error is not a connection failure
- **WHEN** a call reaches the upstream and returns a tool result with `isError: true`
- **THEN** the failure count is reset and a server with `health_status: error` becomes `ok`

### Requirement: UPS-5 Rename guard
Renaming a server MUST be rejected while it is a member of any bundle (the name is baked into prefixed tool names),
unless the rename request carries an explicit `force` flag that acknowledges client-visible tool names will change.

#### Scenario: Renaming a bundle member is refused
- **WHEN** `POST /api/v1/upstreams/{name}:rename?new_name=…` is called for a server that belongs to a bundle
- **THEN** the response is `409` and the server keeps its name

#### Scenario: Force acknowledges the change
- **WHEN** the same rename is retried with `force=true`
- **THEN** the rename succeeds with `200`

### Requirement: UPS-6 Config changes reach every replica
A server config change (url/headers/auth) SHALL publish a `server` invalidation event on the config-invalidation event
stream ([sessions](../sessions/spec.md)) after it commits, and MUST invalidate every
pooled upstream connection and session for that server on every replica
([SES-9](../sessions/spec.md)), so no pooled connection outlives the change: the next call on
any replica connects with the committed config.

#### Scenario: Next call uses the new URL
- **WHEN** a server's `url` is changed through the management API
- **THEN** the next tool call to that server on any replica connects to the new URL

#### Scenario: The change is announced
- **WHEN** a server is created, updated or deleted
- **THEN** an invalidation event with entity type `server` and the server's name is published after the commit

#### Scenario: Pooled connections do not outlive a header change
- **GIVEN** a replica holds a pooled upstream session to server `echo` opened with static header `x-tenant: a`
- **WHEN** the header is changed to `x-tenant: b`
- **THEN** the pooled session is closed and the next call to `echo` sends `x-tenant: b`

### Requirement: UPS-7 Documented stdio sidecar pattern
The docs MUST document how to run a stdio-only MCP server behind bundlemcp: wrap it in a sidecar container exposing
Streamable HTTP (e.g. `mcp-proxy`, Supergateway, or FastMCP's own proxy runner) and register the sidecar's URL. A
compose snippet example is part of the docs deliverable.

#### Scenario: The sidecar guide carries a compose example
- **WHEN** an operator reads [`docs/connect/stdio-sidecar.md`](../../../docs/connect/stdio-sidecar.md)
- **THEN** it names the sidecar options and gives a compose `services:` snippet whose URL is then registered as a server

### Requirement: UPS-8 Egress policy on every upstream request
All gateway-initiated requests to server URLs (probes, discovery, live calls) MUST pass the egress policy
([SEC-1/SEC-2](../security/spec.md)).

#### Scenario: A denied URL is never contacted
- **WHEN** a server's URL points at an address the egress policy refuses
- **THEN** discovery records `connection_state: egress_denied` and no request is sent to that address

### Requirement: UPS-10 Protocol era per upstream
Protocol era per upstream ([PROT-21](../protocol/spec.md)): a server MUST have a `protocol_mode` — `auto`
(default: probe `server/discover`, fall back to `initialize`), `legacy` (always the `initialize` handshake, for
upstreams whose tools need server-initiated requests), or a pinned modern revision (`YYYY-MM-DD`). Discovery records
the negotiated revision as `protocol_version`, shown in the API and UI so an operator can see which upstreams still
speak the handshake era. An update that omits `protocol_mode` keeps the stored value rather than resetting it to
`auto`.

#### Scenario: Omitted mode is kept on update
- **WHEN** a server stored with `protocol_mode: legacy` is updated without `protocol_mode`
- **THEN** it keeps `protocol_mode: legacy`

#### Scenario: Invalid mode is rejected
- **WHEN** a server is written with `protocol_mode: newest`
- **THEN** the API answers `422`

#### Scenario: Negotiated revision is recorded
- **WHEN** discovery succeeds against an upstream
- **THEN** the revision it negotiated is stored as `protocol_version` and returned by the API

### Requirement: UPS-11 Inspection
`POST /api/v1/upstreams:inspect` MUST take a `url` and optional candidate `headers`, store nothing, and report what the
upstream is: its `connection_state` (UPS-12), negotiated `protocol_version`, `serverInfo` (name, title, description,
website), its tools, and — for an OAuth-protected upstream — the authorization server, the scopes the resource asks
for, and how the gateway can identify itself there (`preregistered_required`, `metadata_document`,
`dynamic_registration`; [UPS-25](../upstreams/spec.md)). It returns a suggested `ServerUpsert` (slug-safe name from
`serverInfo`, description, `auth_mode`, `identity_mode`, `send_identity_header`) that a caller can submit as is. Every
request passes the egress policy (UPS-8); candidate header values are used for the probe only and never stored, logged
or echoed. What a server needs is mostly a fact about the upstream, which the gateway can ask it; only the choices the
upstream cannot answer are put to the operator
([ADR-0039](../../../docs/adr/0039-server-inspection-and-connection-state.md)).

#### Scenario: Inspecting a reachable server suggests a config
- **WHEN** `POST /api/v1/upstreams:inspect` is called with the URL of a working MCP server
- **THEN** the response has `connection_state: ready`, the server's `serverInfo` and tools, and a `suggestion` that can
  be submitted to `PUT /api/v1/upstreams/{name}` unchanged

#### Scenario: Inspection stores nothing
- **WHEN** an inspection completes
- **THEN** no server row exists for the inspected URL and the candidate header values appear nowhere in the response

### Requirement: UPS-12 Connection state
Discovery and inspection MUST classify their outcome from the upstream's HTTP response, not from the MCP client's error
text:

| State | Signal |
|---|---|
| `ready` | a valid `server/discover` or `initialize` result |
| `oauth_required` | 401/403 with a `Bearer` challenge naming `resource_metadata`, or a protected resource document at a well-known location |
| `account_required` | the server is `upstream_oauth` and no account is connected to probe with ([UPS-33](../upstreams/spec.md)) |
| `insufficient_scope` | 403 with `error="insufficient_scope"` ([UPS-34](../upstreams/spec.md)) |
| `credential_required` | 401/403 with no OAuth metadata anywhere |
| `not_mcp` | 404/405/406/415 without a JSON-RPC error body, or a non-MCP body |
| `unreachable` | connection, TLS or timeout failure |
| `egress_denied` | the egress policy refused the URL ([SEC-1](../security/spec.md)) |
| `error` | anything else |

The state is stored on the server (`unknown` until the first probe) and shown in the API and UI. A stored state that
contradicts the configured `auth_mode` — `oauth_required` on a server without upstream OAuth, `credential_required` on
one without static headers — is reported as a mismatch the UI offers to fix. OAuth is never started for a server
because of a 401 alone: only an OAuth challenge or document is evidence of OAuth.

#### Scenario: A plain 401 is a credential problem
- **WHEN** the upstream answers 401 without a `Bearer` challenge and no protected resource document exists
- **THEN** the state is `credential_required`, not `oauth_required`

#### Scenario: An OAuth challenge is recognised
- **WHEN** the upstream answers 401 with `WWW-Authenticate: Bearer resource_metadata="…"`
- **THEN** the state is `oauth_required`

#### Scenario: A contradiction is reported
- **WHEN** a server without upstream OAuth is stored with `connection_state: oauth_required`
- **THEN** its API representation carries a non-empty `configuration_mismatch`

### Requirement: UPS-13 Identity header default
`send_identity_header` is optional on write. Omitted when a server is created, it MUST be derived; omitted on an
update, the stored value is kept. The derived value is on for a server on the gateway's own network (a host name
without a dot, `localhost`, a name under `.local`, `.internal`, `.localhost` or `.svc`, or a private, loopback or
link-local address) and off for every other host, so a third-party server never receives caller identifiers unless an
operator opts in.

#### Scenario: Internal host defaults on
- **WHEN** a server with URL `http://weather:8080/mcp` is created without `send_identity_header`
- **THEN** it is stored with `send_identity_header: true`

#### Scenario: Public host defaults off
- **WHEN** a server with URL `https://mcp.example.com/mcp` is created without `send_identity_header`
- **THEN** it is stored with `send_identity_header: false`

### Requirement: UPS-14 Header rules at write time
A `forward_headers` entry whose client or upstream name is on the [AUTH-28](../auth/spec.md) deny-list
MUST be rejected with 422 when the server is written, not only skipped at call time.

#### Scenario: Forwarding a denied header is refused
- **WHEN** a server is written with a `forward_headers` entry mapping to `Host` (or another deny-listed name)
- **THEN** the API answers `422` and nothing is stored

### Requirement: UPS-15 Registry server.json import
`POST /api/v1/upstreams:from-server-json` MUST accept an MCP Registry `server.json` document and return a draft: the
first `streamable-http` remote's URL (URL template variables listed for the operator to fill), a slug-safe name and
description, and the remote's declared `headers` with their `description`, `isRequired` and `isSecret` flags, so the
UI can render the credential form the server's publisher described. It stores nothing and fetches nothing; `sse`
remotes are reported as unsupported. This imports one document an operator already has — it is not a registry browser
(decision log: marketplace).

#### Scenario: A streamable-http remote becomes a draft
- **WHEN** a `server.json` with one `streamable-http` remote and a secret `X-API-Key` header is posted
- **THEN** the draft carries the remote's URL, a slug-safe name and the header with `is_secret: true`, and nothing is
  stored

#### Scenario: SSE-only documents are reported
- **WHEN** a `server.json` whose only remote is `sse` is posted
- **THEN** the draft has no URL and lists the SSE remote as unsupported

### Requirement: UPS-16 Published name
The resource MUST be called an **upstream server**, or **upstream** for short, everywhere a person or a client of the
gateway reads it. On the wire it is always the short form: the management API collection is `/api/v1/upstreams` (with
every sub-route and action of the former `/api/v1/servers` under it), a bundle's members are
`/api/v1/bundles/{name}/upstreams`, the OpenAPI tag is `upstreams`, the bootstrap and export documents use the key
`upstreams` ([MGMT-15](../management/spec.md), [MGMT-17](../management/spec.md)), the admin UI routes are
`/upstreams` and its navigation and list page say *Upstream servers*, and the documentation introduces the term as
"upstream server (upstream for short)" and may use either afterwards. "Server" alone is ambiguous next to the gateway,
which is itself an MCP server to its clients and an HTTP server to everyone. Field names inside payloads
(`server_name`, `server_id`, the metering context's `server`) are unchanged: each is already qualified by the object it
sits on, and the metering hook contract is versioned separately ([PROT-26](../protocol/spec.md)). The
old names are not kept as aliases: `/api/v1/servers` answers `404` and a bootstrap or import document using `servers`
is rejected ([ADR-0045](../../../docs/adr/0045-upstreams-on-the-published-surface.md)).

#### Scenario: The former paths are gone
- **WHEN** `GET /api/v1/servers/weather` or `GET /api/v1/bundles/b1/servers` is requested
- **THEN** the response is `404`

#### Scenario: OpenAPI uses the short form
- **WHEN** the OpenAPI document is read
- **THEN** it has the tag `upstreams` and no tag `servers`

#### Scenario: An old bootstrap document is rejected
- **WHEN** a bootstrap document uses the top-level key `servers`
- **THEN** it is rejected with a validation error rather than misread

#### Scenario: The export uses the short form
- **WHEN** `GET /api/v1/export` is called
- **THEN** the document lists upstream servers under the key `upstreams` and has no key `servers`

### Requirement: UPS-17 Discovery triggers
Discovery MUST run on server create and on an update that needs it ([UPS-2](../upstreams/spec.md)), including
a bootstrap upsert once its document has committed ([MGMT-14](../management/spec.md)), on explicit "refresh tools" from
UI/API, on the periodic refresh (UPS-23), and after an upstream OAuth connect completes
([UPS-33](../upstreams/spec.md)). An endpoint's `tools/list` is served from the cache (UPS-20) and never reaches an
upstream, so serving it does not trigger discovery; the periodic refresh covers what that would have caught
([ADR-0038](../../../docs/adr/0038-periodic-tool-refresh.md)). An `upstream_oauth` server is probed with a connected
account's bearer; until one exists it is reported as not connected, not as failing. A discovery that changes the tool
set invalidates every bundle containing the server, so live clients re-list ([BND-7](../bundles/spec.md)).

#### Scenario: Explicit refresh runs discovery now
- **WHEN** `POST /api/v1/upstreams/{name}:refresh-tools` is called
- **THEN** the upstream is probed synchronously and the response reports how many tools were discovered and changed

#### Scenario: Bootstrap probes only after commit
- **WHEN** a bootstrap document registers a server
- **THEN** the server's discovery runs after the document's transaction has committed, never before

#### Scenario: Unconnected OAuth server is not failing
- **WHEN** an `upstream_oauth` server with no connected account is discovered
- **THEN** its `connection_state` becomes `account_required` and its failure count and `health_status` are untouched

#### Scenario: A changed tool set is announced
- **WHEN** discovery finds a new or changed tool on a server that is a member of bundle `b1`
- **THEN** an invalidation event for bundle `b1` is published after the commit

### Requirement: UPS-18 Hash-based sync
Sync is hash-based: the gateway MUST compute a stable hash per tool definition and rewrite a cached definition only when
its hash changed (metamcp's `tools-sync-cache` behavior). A discovery run in which no tool is new, changed, vanished or
reappeared MUST NOT write any cached tool, so the common case is write-free. A new, changed, vanished or reappearing
tool counts as a change of the tool set ([BND-7](../bundles/spec.md)); an unchanged tool does not.

#### Scenario: Unchanged definition is not rewritten
- **WHEN** discovery sees a tool whose definition hash equals the cached `schema_hash`
- **THEN** its definition columns are left as they were and the run reports zero changes

#### Scenario: Unchanged run writes no tool
- **WHEN** discovery of a server lists exactly the tools it listed on the previous successful run, with unchanged
  definitions
- **THEN** no cached tool of that server is written and no bundle is invalidated

#### Scenario: Changed definition is rewritten
- **WHEN** an upstream changes a tool's description
- **THEN** the cached definition and `schema_hash` are updated and the run reports one change

### Requirement: UPS-19 Vanished tools are kept
Tools that disappear from the upstream MUST NOT be deleted automatically: a tool that the latest successful discovery
of its server did not list is **stale**. A stale tool MUST NOT be served — it is absent from every endpoint's
`tools/list` and rejected on `tools/call` like an unknown tool — but keeps its `BundleTool` curation, and is served
again, with that curation, if a later discovery lists it. A failed probe makes no tool stale. The management API and
UI report which tools are stale. Explicit deletion MUST be available as "refresh & prune" in the API and UI: a refresh
that, only when its probe succeeds, deletes the server's stale tools together with their curation in every bundle.

#### Scenario: A vanished tool stays cached
- **WHEN** an upstream that listed `alpha` and `beta` is rediscovered listing only `alpha`
- **THEN** both tools remain cached, `beta` keeps its curation and is reported stale
- **AND** `tools/list` on an endpoint of a bundle containing the upstream lists `alpha` but not `beta`, and a call to
  `beta` is rejected as an unknown tool without contacting the upstream

#### Scenario: A reappearing tool is served with its curation
- **GIVEN** stale tool `beta` with `override_name` `b` in a bundle
- **WHEN** a later discovery lists `beta` again
- **THEN** `beta` is no longer stale and is listed as `b` on the bundle's endpoints

#### Scenario: A failed probe makes nothing stale
- **WHEN** discovery of a server fails
- **THEN** none of its cached tools becomes stale

#### Scenario: Refresh and prune deletes stale tools
- **GIVEN** a server with stale tool `beta`
- **WHEN** an admin calls `POST /api/v1/upstreams/{name}:refresh-tools?prune=true` and the probe succeeds
- **THEN** `beta` and its curation in every bundle are deleted and the response reports one pruned tool

#### Scenario: Prune after a failed probe deletes nothing
- **WHEN** an admin calls `POST /api/v1/upstreams/{name}:refresh-tools?prune=true` and the probe fails
- **THEN** no tool is deleted and the response reports the failure

### Requirement: UPS-20 tools/list works from the cache
Serving `tools/list` on an endpoint MUST work from the Postgres cache when the upstream is unreachable, with the
failure surfaced in `health_status` ([UPS-4](../upstreams/spec.md)) and logged — a degraded response MUST be
observable, never silent (metamcp's silent-partial-failure hazard).

#### Scenario: Upstream down, tools still listed
- **WHEN** a member server is unreachable and a client calls `tools/list` on an endpoint of its bundle
- **THEN** the response lists the server's cached tools without contacting the upstream

#### Scenario: Failed probes are logged
- **WHEN** a discovery probe fails
- **THEN** a `discovery.failed` warning naming the server and the connection state is logged

### Requirement: UPS-21 Schemas stored verbatim
Tool input schemas MUST be stored verbatim (json) and served unmodified unless a profile or override transforms them.

#### Scenario: Schema round-trips unchanged
- **WHEN** an upstream tool's `inputSchema` is discovered and the tool is then listed on an endpoint
- **THEN** the listed `inputSchema` is identical to the upstream's

### Requirement: UPS-22 Capability snapshot
Discovery MUST also capture the server's **advertised capabilities** from the upstream `initialize` (or
`server/discover`) result (which of tools/prompts/resources/completions/logging it supports, plus
`listChanged`/`subscribe` flags) into `McpServer.capabilities` ([UPS-1](../upstreams/spec.md),
[architecture](../architecture/spec.md)). This snapshot is the source for capability aggregation
([PROT-11](../protocol/spec.md)) so `initialize` need not fan out to members. Refreshed on every discovery
run; degrade-observably on failure (UPS-20), keeping the last-known snapshot.

#### Scenario: Snapshot is stored at discovery
- **WHEN** discovery succeeds against an upstream advertising `prompts` and `resources`
- **THEN** the server's `capabilities` carries both, as returned by the API

#### Scenario: Failure keeps the last snapshot
- **WHEN** a later discovery of the same server fails
- **THEN** the stored `capabilities` are unchanged

### Requirement: UPS-23 Periodic refresh
Periodic refresh: every `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL` seconds (default 1800; `0` disables it) the gateway MUST
re-run discovery for every registered server, one server at a time. Only one replica refreshes per interval: the run
takes a shared, self-expiring lease in Valkey, and a replica that finds it held skips that tick. Each run is an
ordinary discovery, so a changed tool set is announced (BND-7), and failures count toward `health_status` like any other
probe ([UPS-4](../upstreams/spec.md)): because the failure count is shared by every replica, an
upstream that stays unreachable is marked `error` after `server_error_attempts` refreshes instead of staying `unknown`,
whichever replica ran each sweep. One server's failure never stops the run for the rest, and every discovery probe is
bounded (60 s) so a hanging upstream fails instead of stalling the run. This covers the upstreams the other triggers
miss: one that was unreachable when it was registered, and one whose tools change while no call is open to it.
Per-call upstream connections ([ADR-0012](../../../docs/adr/0012-per-call-upstream-connections.md)) never
receive a `list_changed` sent between calls ([PROT-10](../protocol/spec.md) residual).
Rationale and the alternatives weighed: [ADR-0038](../../../docs/adr/0038-periodic-tool-refresh.md).

#### Scenario: One replica sweeps per interval
- **WHEN** two replicas reach the same refresh tick
- **THEN** only the one that takes the lease runs the sweep; the other skips the tick

#### Scenario: One failing server does not stop the sweep
- **WHEN** one server's probe fails or hangs past 60 s during a sweep
- **THEN** it is counted as failed and every other server is still probed

#### Scenario: Interval 0 disables the refresh
- **WHEN** `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL=0`
- **THEN** no periodic sweep runs

#### Scenario: An upstream that stays down is marked as failing
- **GIVEN** `server_error_attempts` is `3` and a server that was unreachable when it was registered
- **WHEN** three consecutive sweeps, run by different replicas, fail to reach it
- **THEN** its `health_status` is `error` rather than `unknown`

### Requirement: UPS-25 Client identity and authorization server discovery
A server with `auth_mode=upstream_oauth` ([UPS-1](../upstreams/spec.md)) needs a client identity at the
upstream authorization server. The gateway SHALL use the MCP authorization spec's priority order
([ADR-0040](../../../docs/adr/0040-upstream-client-identification.md)):

1. a **pre-registered** client id/secret an admin stored — always wins;
2. a **Client ID Metadata Document**: when the authorization server advertises `client_id_metadata_document_supported`
   and accepts `none` as a token endpoint auth method, the gateway's client id is the URL of its own published
   document, `{public_base}/oauth/upstream/client.json` (public client, PKCE, the gateway's callback as the only
   redirect URI) — nothing is registered or stored;
3. **dynamic registration** (RFC 7591, deprecated by the MCP spec but kept for authorization servers without CIMD):
   the gateway registers as a public client (`token_endpoint_auth_method: none`, `application_type: web`, grants
   `authorization_code` + `refresh_token`, the callback as the only redirect URI) and stores the registration with the
   metadata and issuer it was made against;
4. otherwise the connect fails with "the admin has to store a client", and inspection
   ([UPS-11](../upstreams/spec.md)) reports `preregistered_required` before anyone tries.

The authorization server is found the way the MCP authorization spec orders it: the `resource_metadata` a 401 from the
server names in `WWW-Authenticate`, then the RFC 9728 document path-inserted for the server's path, then at the
origin; its metadata through RFC 8414 (path-inserted) or OpenID Connect discovery. Every URL on that chain passes the
egress policy ([SEC-1](../security/spec.md)). The connect requests the scopes the **protected resource** asks for — the
`scope` of its 401 challenge, else its resource document's `scopes_supported` — and no `scope` at all when it names
none, leaving the authorization server to apply the client's defaults. Endpoints that were remembered or entered by an
admin carry no resource scopes, so the resource is asked again at connect time rather than requesting nothing. The
authorization server's own `scopes_supported` is never requested: it is the server's whole catalogue, and a server
refuses the entire request over one scope the client was not granted. The challenge is obtained with an
unauthenticated `POST` of an MCP request (`server/discover`), because a stateless server answers `GET` with 405 before
it ever challenges.

#### Scenario: Pre-registered client wins
- **WHEN** an admin stored a client id for a server whose authorization server also supports CIMD and DCR
- **THEN** the connect uses the stored client id

#### Scenario: CIMD client id
- **WHEN** no client is stored and the authorization server advertises `client_id_metadata_document_supported` and the
  `none` auth method
- **THEN** the authorize redirect's `client_id` is `{public_base}/oauth/upstream/client.json` and nothing is registered

#### Scenario: Neither CIMD nor DCR
- **WHEN** no client is stored and the authorization server supports neither CIMD nor registration
- **THEN** the connect fails telling the admin to store a client, and inspection reports `preregistered_required`

#### Scenario: Requested scopes come from the protected resource
- **WHEN** the server's 401 challenge names `scope="read write"` and the authorization server lists more scopes
- **THEN** the authorize request asks for exactly `read write`

### Requirement: UPS-26 Token storage per user
Token storage SHALL be keyed `(server_id, user_id)`; `user_id = NULL` is the **shared/service connection**
established by an admin from the UI. Per-server setting `identity_mode`: `shared` (all callers use the NULL row —
metamcp behavior) or `per_user` (each caller must connect their own account).

#### Scenario: Shared mode uses the shared row
- **WHEN** any caller calls a tool of a `shared` server
- **THEN** the gateway uses the connection with no user

#### Scenario: Per-user mode uses the caller's row
- **WHEN** a signed-in user calls a tool of a `per_user` server
- **THEN** the gateway uses that user's own connection, never another user's

### Requirement: UPS-27 Interactive connect flow
The gateway SHALL offer an interactive connect flow: from the server detail page (admin, shared mode) — and, for
`per_user` mode, from a minimal hosted "connect your account" page a user is directed to when calling a tool that lacks
a token for them. The state parameter is server-generated, single-use, stored server-side (metamcp's CSRF fix carried
over). PKCE is used when supported. Because a user with no token may have no tool to call yet, `tools/list` also
offers a signed-in caller who has no valid token for a `per_user` member server a gateway-provided tool
`<server>__connect_account` ([ADR-0037](../../../docs/adr/0037-connect-account-tool.md)). Calling it returns the
connect URL as a normal result; it reaches no upstream and is not metered. It is not listed once the caller holds a
valid token, stays callable to connect a different account, and never shadows an upstream tool presenting the same
name. API-key and anonymous callers are not offered it: a per-user connection is keyed by a user.

#### Scenario: Unconnected user sees the connect tool
- **WHEN** a signed-in user without a valid token for a `per_user` member server lists tools
- **THEN** the list includes `<server>__connect_account`, and calling it returns the connect URL without reaching the
  upstream or metering

#### Scenario: Connected user does not see it
- **WHEN** the same user lists tools after connecting
- **THEN** `<server>__connect_account` is not listed, but calling it still returns the connect URL

#### Scenario: State is single-use
- **WHEN** a connect callback is replayed with a state that was already consumed
- **THEN** the callback is rejected and no token is stored

#### Scenario: API-key caller is not offered the tool
- **WHEN** an API-key caller lists tools of a bundle with a `per_user` server
- **THEN** no `__connect_account` tool is listed

### Requirement: UPS-28 Refresh on 401
On upstream 401/token-expiry the gateway SHALL refresh with the stored refresh token (or, for a client-credentials
client, a new grant — UPS-35) and retry the original request once. The retry is triggered by the upstream's 401
itself, observed on the HTTP response, not by any failed call; if refresh fails, the gateway surfaces a structured MCP
error telling the caller (or admin) to re-connect, and marks the token row invalid. Refresh MUST be single-flight per
token row (Redis lock) to avoid stampedes.

#### Scenario: 401 triggers one refresh and retry
- **WHEN** an upstream answers a tool call with HTTP 401
- **THEN** the gateway refreshes the token and retries the call once with the new token

#### Scenario: Failed refresh asks to reconnect
- **WHEN** the refresh is refused by the authorization server
- **THEN** the caller receives a structured error carrying the connect URL and the token row is marked invalid

#### Scenario: Concurrent refreshes are single-flight
- **WHEN** several calls hit an expired token for the same row at once
- **THEN** only one refresh request reaches the authorization server

### Requirement: UPS-29 Token confidentiality
Upstream tokens MUST be encrypted at rest ([ARC-18](../architecture/spec.md)), never logged, never returned by any API.
The UI shows connection status (connected/expired/error + account hint) only.

#### Scenario: Status without secrets
- **WHEN** an admin reads a server's upstream connection status
- **THEN** the response carries the status and an account hint, and no access or refresh token value

### Requirement: UPS-30 Per-user servers need an identified caller
`per_user` calls MUST resolve the caller identity from the request context ([EP-6](../endpoints/spec.md)); an
unauthenticated (`none`-auth) endpoint cannot serve `per_user` upstream servers. The invariant is enforced at
**every** mutation that could violate it: endpoint create/update, bundle membership changes, and switching a server's
`identity_mode`.

#### Scenario: none-auth endpoint over a per-user server is refused
- **WHEN** an admin creates a `none`-auth endpoint for a bundle containing a `per_user` server
- **THEN** the management API refuses the change

#### Scenario: Switching identity mode is checked too
- **WHEN** an admin switches a server to `per_user` while a bundle containing it is served by a `none`-auth endpoint
- **THEN** the change is refused

### Requirement: UPS-31 Introspecting upstreams authenticate
Upstreams that verify forwarded bearers against `/oauth/introspect` ([AUTH-30](../auth/spec.md)) MUST
authenticate to it with their own `service`-kind API key ([AUTH-23](../auth/spec.md)) provisioned by the admin —
introspection is never anonymous ([AUTH-5](../auth/spec.md)).

#### Scenario: Upstream introspects with a service key
- **WHEN** an upstream introspects a forwarded token using a service-kind key
- **THEN** it receives the token's introspection result
- **AND** without a key it receives 401

### Requirement: UPS-32 Issuer validation (RFC 9207)
The connect flow SHALL record the upstream authorization server's `issuer` from its validated metadata in the
single-use state before redirecting, and on callback apply the RFC 9207 §2.4 rule: an `iss` that is present MUST equal
the recorded issuer (string comparison, no normalisation) or the callback is rejected before the code is redeemed; an
absent `iss` is rejected when the server's metadata advertises `authorization_response_iss_parameter_supported`.
Stored credentials are bound to the issuer that granted them and are never presented to another authorization server.

#### Scenario: Mismatched iss is rejected
- **WHEN** a connect callback carries an `iss` different from the recorded issuer
- **THEN** the callback is rejected and the code is never redeemed

#### Scenario: Missing iss where advertised
- **WHEN** the authorization server advertises `authorization_response_iss_parameter_supported` and the callback has
  no `iss`
- **THEN** the callback is rejected

### Requirement: UPS-33 Discovery with upstream credentials
Tool discovery ([UPS-17](../upstreams/spec.md)) of an `upstream_oauth` server SHALL send a bearer: the shared
connection's for `shared` mode, any user's valid connection's for `per_user` mode (tool lists rarely depend on the
caller, and without some user's token the server cannot be asked at all). With no connection to use, discovery reports
"upstream not connected" without counting it toward the server's error streak ([UPS-4](../upstreams/spec.md)).
A completed connect triggers discovery and invalidates the server's bundles, so live clients receive
`tools/list_changed` ([BND-7](../bundles/spec.md)).

#### Scenario: Unconnected server is not an error
- **WHEN** discovery runs for an `upstream_oauth` server nobody has connected
- **THEN** it reports "upstream not connected" and the server's consecutive-failure count does not grow

#### Scenario: Per-user server borrows a user's connection
- **WHEN** discovery runs for a `per_user` server one user has connected
- **THEN** the tool listing is requested with that user's bearer

#### Scenario: Connect refreshes tools
- **WHEN** a connect completes
- **THEN** discovery of the server is scheduled and its bundles' live clients receive `tools/list_changed`

### Requirement: UPS-34 Scope step-up
A 403 with `error="insufficient_scope"` from an upstream on a call ([UPS-12](../upstreams/spec.md)) MUST NOT be
retried blindly: the challenge's `scope` is added to the scopes the server's next connect requests (the union with what
was requested before), and the caller receives the structured reconnect error of UPS-28 naming the missing permission,
so reconnecting grants it. The step-up scopes are stored with the server's client configuration and survive restarts.

#### Scenario: Insufficient scope widens the next connect
- **WHEN** an upstream answers a call with 403 `insufficient_scope` and `scope="admin"`
- **THEN** the caller receives a reconnect error naming `admin`
- **AND** the next connect for that server requests the earlier scopes plus `admin`

### Requirement: UPS-35 Client credentials
For a shared upstream that authorizes a machine rather than a person, an admin MAY store the client with
`grant_type: client_credentials` (the MCP OAuth Client Credentials extension). The gateway SHALL then obtain and renew
tokens with the `client_credentials` grant — client secret in the request body, `resource` and resource scopes
included — without any browser connect; "Connect" performs the grant immediately. Such a client requires
`identity_mode=shared`, a client secret, and an authorization server whose `grant_types_supported` (when advertised)
includes `client_credentials`. JWT client assertions (RFC 7523) are not supported.

#### Scenario: Connect performs the grant
- **WHEN** an admin presses Connect on a server whose stored client uses `client_credentials`
- **THEN** the gateway obtains a token directly from the token endpoint, with no browser redirect

#### Scenario: Per-user server cannot use client credentials
- **WHEN** an admin stores a `client_credentials` client for a `per_user` server, or without a client secret
- **THEN** the change is refused

### Requirement: UPS-36 Resource indicators
Every authorization request, token request and refresh request SHALL carry the RFC 8707 `resource` parameter: the
protected resource document's `resource` when it is a parent of the server URL, otherwise the canonical server URL —
whether or not the authorization server advertises support.

#### Scenario: Resource on every request
- **WHEN** the gateway connects to and later refreshes against an upstream authorization server
- **THEN** the authorize, token and refresh requests all carry the same `resource` value

### Requirement: UPS-37 Metadata the gateway refuses
Discovery SHALL reject authorization server metadata that does not list `S256` in `code_challenge_methods_supported`
(the connect cannot use PKCE), and metadata whose `issuer` differs from the issuer the document was fetched for. A
dynamically registered client is bound to the issuer it was registered at: when the server's authorization server
changes, the stored registration is discarded and the gateway registers again. An admin-stored client is never
discarded; a connect against a different issuer than it was stored for is refused with a message naming both.

#### Scenario: No S256 support
- **WHEN** the authorization server's metadata omits `S256` from `code_challenge_methods_supported`
- **THEN** the connect is refused

#### Scenario: Authorization server moved
- **WHEN** a server whose client was dynamically registered now points at a different issuer
- **THEN** the old registration is discarded and the gateway registers again
- **AND** for an admin-stored client the connect is refused with a message naming both issuers

### Requirement: UPS-24 Prompt and resource discovery
When a discovery probe reaches a server whose capability snapshot ([UPS-22](../upstreams/spec.md))
advertises `prompts`, the gateway SHALL also list its prompts. When the snapshot advertises `resources`, it SHALL also
list its resources and resource templates. Each listing is read to its last page and kept two ways:

- **For curation:** per entry, the prompt name or resource URI with its title and description, hash-gated like tools
  (UPS-18) and kept, not deleted, when they vanish (UPS-19). Resource templates are not curated.
- **As a listing snapshot:** the whole listing exactly as the server listed it, entry by entry and in its order, with
  the `cacheScope` the server put on the wire, if any, and whether the listing was complete. Endpoints serve lists from
  this snapshot when it may be shared (UPS-38, [BND-8](../bundles/spec.md)).

Neither holds prompt messages or resource content. The number of entries kept per server and kind is bounded; a longer
listing is cached truncated for curation, its snapshot is marked incomplete, and the truncation is logged. A listing
that fails leaves both as they were. A probe whose listings differ from the stored snapshots announces the change to
the clients of every bundle the server is an enabled member of, as prompt or resource list changes, the way the
member's own list-change notification is announced ([PROT-10](../protocol/spec.md)).

#### Scenario: Prompts are cached at discovery
- **WHEN** discovery succeeds against an upstream advertising `prompts` that lists prompts `daily` and `weekly`
- **THEN** both prompts are cached for the server with their titles and descriptions, and no prompt messages are stored

#### Scenario: The listing is stored as listed
- **WHEN** discovery succeeds against an upstream advertising `resources` that lists a resource with a MIME type and
  a resource template, across two pages
- **THEN** the stored snapshots hold both pages' entries in the server's order, each with every field the server
  listed

#### Scenario: A server without the capability is not asked
- **WHEN** discovery succeeds against an upstream whose snapshot does not advertise `resources`
- **THEN** the upstream receives no `resources/list` or `resources/templates/list` request

#### Scenario: A failed listing keeps the cache
- **WHEN** a later discovery of the same server fails before or while listing its prompts
- **THEN** the cached prompts and the prompt snapshot are unchanged

#### Scenario: A long resource listing is truncated observably
- **WHEN** an upstream lists more resources than the bound
- **THEN** only the bound is cached for curation, the resource snapshot is marked incomplete, and a warning naming the
  server is logged

#### Scenario: A changed listing is announced
- **GIVEN** a client holds an open stream on an endpoint of a bundle with member `docs`
- **WHEN** an explicit refresh of `docs` finds a resource that its stored snapshot does not have
- **THEN** the client receives `notifications/resources/list_changed`

### Requirement: UPS-38 Shared listing snapshots
A listing snapshot (UPS-24) SHALL be served to every caller of a bundle only when it is **shareable**. A server's
`listing_snapshot` setting decides how, and is `auto` unless set on write:

- **`auto`:** a listing the server marked `cacheScope: public` is shareable, and one marked `cacheScope: private` is
  not. A listing without a scope, as servers before revision 2026-07-28 send it, is shareable only when nothing the
  server is sent depends on the caller. That holds when the server forwards no client headers, is not sent the
  caller's identity, and authenticates neither per user nor with a token delegated per caller.
- **`shared`:** every listing is shareable, whatever scope the server gave. An operator chooses it for a server that
  is sent the caller's identity but lists the same for everyone, or one that marks every result `private` because
  that is its SDK's default on revision 2026-07-28.
- **`live`:** no listing is shareable, so the server is always asked.

An incomplete snapshot is never served. A server's `ttlMs` on a list result does not expire its snapshot; the snapshot
is replaced by the next discovery of that server ([UPS-17](../upstreams/spec.md), [UPS-23](../upstreams/spec.md),
[PROT-10](../protocol/spec.md)). The setting is part of the server's management API representation and of the
configuration document ([MGMT-9](../management/spec.md)); changing it does not probe the server.

#### Scenario: An identity-free server's listing is shared
- **GIVEN** a server with no forwarded headers, no identity header and a shared credential, whose prompt listing had
  no `cacheScope`
- **WHEN** its snapshot is checked for serving under `auto`
- **THEN** it is shareable

#### Scenario: A server sent the caller's identity is not shared
- **GIVEN** a server that forwards the caller's `Authorization` header, whose prompt listing had no `cacheScope`
- **WHEN** its snapshot is checked for serving under `auto`
- **THEN** it is not shareable

#### Scenario: The server's scope decides when it gave one
- **GIVEN** a server sent the caller's identity, whose listing was marked `cacheScope: public`, and an identity-free
  server whose listing was marked `cacheScope: private`
- **WHEN** both snapshots are checked for serving under `auto`
- **THEN** the first is shareable and the second is not

#### Scenario: An operator shares or refuses explicitly
- **GIVEN** a server sent the caller's identity header, whose listing was marked `cacheScope: private`
- **WHEN** its snapshot is checked under `shared`, and again under `live`
- **THEN** it is shareable under `shared` and not under `live`

#### Scenario: The setting round-trips
- **WHEN** an admin upserts a server with `listing_snapshot: shared` and later upserts it without the field
- **THEN** `GET /api/v1/upstreams/{name}` reports `listing_snapshot: shared` both times, and neither write probes the
  server for that field

## Out of scope

### Upstream registry

- STDIO and SSE upstream transports (decision log).
- Auto-discovery of servers (the application layer's registrar does that, via the management API).

### Tool discovery

- **Serving** resources and prompts is handled in [bundles](../bundles/spec.md) (pass-through). Their listings are
  stored for curation and for the list methods (UPS-24, UPS-38), never their content.

### Upstream OAuth

- Being an IdP or brokering identities between upstreams.
- Token sharing across bundlemcp instances that don't share the database.

## Notes

### Upstream registry

Origin: metamcp carry-over, narrowed to Streamable HTTP. Prior art: `../metamcp/apps/backend/src/db/schema.ts`
(`mcp_servers`), `../metamcp/packages/zod-types/src/mcp-servers.zod.ts`.

Open question: per-server request timeout overrides vs. global-only (lean: global `Config` values first, per-server
later if needed).

### Tool discovery

Origin: metamcp carry-over. Prior art: `../metamcp/apps/backend/src/lib/metamcp/fetch-metamcp.ts`,
`tools-sync-cache.ts`.

Upstream `tools/list_changed`: required by [PROT-10](../protocol/spec.md), with downstream propagation per
[BND-7](../bundles/spec.md). Per-call upstream connections cannot receive a `list_changed` sent between calls (PROT-10
residual), and the gateway does not yet re-discover on one received during a call; the periodic refresh (UPS-23) bounds
how stale the cache gets meanwhile.

A tool that vanished upstream is still presented by `tools/list` until it is disabled in the bundle; the cache keeps
it, and nothing filters stale tools out of the served set. There is no "refresh & prune" operation yet.

### Upstream OAuth

Origin: improvement — metamcp stored one token set per server; bundlemcp stores one per (server, user). Prior art:
`../metamcp/apps/backend/src/lib/oauth-upstream/`, `oauth_sessions` table,
`../metamcp/apps/backend/src/trpc/pre-registered-oauth.ts`.

The per-user connect prompt is a structured MCP error carrying the connect URL
([ADR-0017](../../../docs/adr/0017-upstream-oauth-encryption.md)) — reliable across clients and independent of a live
elicitation channel. Elicitation-based connect is deferred (the relay already supports it, so it can be added without
rework). Amended by [ADR-0037](../../../docs/adr/0037-connect-account-tool.md): the error stays for calls to a
server's tools, and the `<server>__connect_account` tool is added so a user with no tools yet can still reach the URL.
