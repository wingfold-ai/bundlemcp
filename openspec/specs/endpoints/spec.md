# endpoints Specification

## Purpose

The public URLs that serve a bundle, each shaped for one kind of client. One bundle can have many endpoints, each with
its own URL, accepted authentication modes (OAuth, API key, none), profile and rate limits. Profiles adapt the tool
surface to a client's quirks: claude, chatgpt (which re-annotates write tools so ChatGPT accepts them) and default. Rate
limits hold across all replicas through shared counters, answer 429 with Retry-After, and include the limiter on
authentication failures.

How a credential is issued and validated is the auth slice; what the endpoint serves is the bundles and protocol slices.

It merges what were separate specs until 2026-10-13: Endpoints, Endpoint profiles, Rate limiting.

## Requirements

### Requirement: EP-1 URL scheme and reserved names
URL scheme: `POST https://<host>/{endpoint_name}/mcp` (Streamable HTTP). `endpoint_name` MUST be globally unique,
slug-safe, and MUST NOT be a reserved first path segment (`api`, `oauth`, `.well-known`, `healthz`, `readyz`,
`metrics`, `docs`, `login`, `consent`, `static` — validated at write time). No SSE (`/sse`) and no REST bridge
(`/api`) routes exist (decision log). The one endpoint SHALL serve every supported protocol revision
([PROT-13](../protocol/spec.md)): modern-era clients (2026-07-28+) use POST only; `GET` and `DELETE` without
an `Mcp-Session-Id` MUST answer `405 Method Not Allowed`.

#### Scenario: Reserved name is rejected on write
- **WHEN** an admin creates an endpoint named `api`
- **THEN** the management API rejects the write with a validation error naming the reserved name

#### Scenario: GET and DELETE without a session are 405
- **WHEN** a client sends `GET /main/mcp` or `DELETE /main/mcp` without an `Mcp-Session-Id` header
- **THEN** the gateway answers `405 Method Not Allowed` with `Allow: POST`

### Requirement: EP-1a Session-era GET stream and DELETE
*(handshake-era clients)* `GET /{endpoint_name}/mcp` (the server→client event stream) and `DELETE` (session end) MUST
be supported for a request carrying a valid `Mcp-Session-Id` — the GET stream carries list-changed notifications,
server→client requests, and out-of-call messages required by [protocol passthrough](../protocol/spec.md).
Modern clients obtain the equivalent stream with `subscriptions/listen` ([PROT-17](../protocol/spec.md)).

#### Scenario: Session client opens the event stream
- **GIVEN** a handshake-era client holding a valid `Mcp-Session-Id`
- **WHEN** it sends `GET /{endpoint_name}/mcp` with that header
- **THEN** the gateway answers with a `text/event-stream` response that delivers list-changed notifications

#### Scenario: Session client ends its session
- **GIVEN** a handshake-era client holding a valid `Mcp-Session-Id`
- **WHEN** it sends `DELETE /{endpoint_name}/mcp` with that header
- **THEN** the session is ended and later requests with that session id are refused

### Requirement: EP-2 Endpoint belongs to one bundle
An endpoint MUST reference exactly one bundle; a bundle may have any number of endpoints. Deleting a bundle SHALL
delete its endpoints ([ARC-17](../architecture/spec.md)).

#### Scenario: Several endpoints over one bundle
- **WHEN** an admin creates endpoints `main` and `gpt`, both with `bundle_name` `tools`
- **THEN** both endpoints serve the tools of bundle `tools`

#### Scenario: Deleting a bundle deletes its endpoints
- **GIVEN** bundle `tools` with endpoint `main`
- **WHEN** the bundle is deleted
- **THEN** endpoint `main` no longer exists and `POST /main/mcp` answers 404

### Requirement: EP-3 Per-endpoint auth modes
Each endpoint SHALL have a non-empty set of **auth modes** (`auth_modes`):

- `oauth` — bearer token issued by bundlemcp's OAuth server ([OAuth server](../auth/spec.md));
- `api_key` — `Authorization: Bearer bmcp_sk_…` or `X-API-Key` header ([API keys](../auth/spec.md));
- `none` — public, only valid alone and requires an explicit `allow_unauthenticated=true` flag on write.

A request MUST be accepted if it satisfies **any** configured mode. 401 responses MUST include the `WWW-Authenticate`
challenge and OAuth protected-resource metadata pointers that MCP clients (claude.ai) need for discovery.

#### Scenario: Unauthenticated request gets the discovery challenge
- **GIVEN** an endpoint `main` with `auth_modes: [oauth]`
- **WHEN** a client posts to `/main/mcp` without credentials
- **THEN** the gateway answers 401 with `WWW-Authenticate: Bearer resource_metadata="…"` pointing at the endpoint's
  protected-resource metadata

#### Scenario: `none` must be alone and confirmed
- **WHEN** an admin writes an endpoint with `auth_modes: [none, api_key]`, or with `auth_modes: [none]` without
  `allow_unauthenticated: true`
- **THEN** the management API rejects the write with a validation error

#### Scenario: Any configured mode admits the request
- **GIVEN** an endpoint with `auth_modes: [oauth, api_key]`
- **WHEN** a client presents a valid API key for that endpoint and no bearer token
- **THEN** the request is accepted

### Requirement: EP-3a OAuth audience binding
OAuth bearers MUST be accepted only when the token's audience matches this endpoint
([AUTH-10](../auth/spec.md)); an audience mismatch is a 401 with the same `WWW-Authenticate` challenge as an
unauthenticated request, prompting the client to re-authorize for this endpoint.

#### Scenario: Token issued for another endpoint is refused
- **GIVEN** an access token issued for endpoint `ep1`
- **WHEN** the client presents it at `/ep2/mcp`
- **THEN** the gateway answers 401 with the `WWW-Authenticate` challenge for `ep2`

### Requirement: EP-3b Credential precedence
When a request satisfies multiple modes (e.g. valid OAuth bearer *and* API key present), precedence MUST be
**oauth > api_key**; the winning identity SHALL be used consistently for metering, audit, rate limiting, and identity
forwarding.

#### Scenario: Valid bearer wins over an API key
- **GIVEN** an endpoint with `auth_modes: [oauth, api_key]`
- **WHEN** a request carries a valid OAuth bearer for that endpoint and a valid `X-API-Key`
- **THEN** the caller identity is the OAuth user, not the API key

### Requirement: EP-4 Profile and rate limits per endpoint
Each endpoint SHALL have a `profile` shaping its tool surface ([endpoint profiles](../endpoints/spec.md)) and
optional rate limits ([rate limiting](../endpoints/spec.md)).

#### Scenario: Two endpoints present one bundle differently
- **GIVEN** endpoints `main` (profile `default`) and `gpt` (profile `chatgpt`) over the same bundle
- **WHEN** a client lists tools on each
- **THEN** `gpt` presents every tool with `readOnlyHint: true` while `main` passes annotations through

### Requirement: EP-5 Disabled endpoint
An endpoint with `enabled=false` MUST return 404 without its configuration being deleted.

#### Scenario: Disabled endpoint is not found
- **GIVEN** endpoint `main` with `enabled: false`
- **WHEN** a client posts to `/main/mcp`
- **THEN** the gateway answers 404
- **AND** `GET /api/v1/endpoints/main` still returns the endpoint's configuration

### Requirement: EP-6 Caller identity on the request context
The resolved caller identity (user `sub` via OAuth, or API key id) MUST be attached to the request context —
middleware ([protocol](../protocol/spec.md)), audit ([audit log](../operations/spec.md)), and identity forwarding
([identity forwarding](../auth/spec.md)) all read it from there, never from tool arguments.

#### Scenario: Per-client rate limit keys on the resolved identity
- **GIVEN** an endpoint with a per-client rate limit and two API keys
- **WHEN** one key exhausts its budget
- **THEN** the other key's calls are still admitted, regardless of any identity claimed in tool arguments

### Requirement: EP-7 Endpoint management and connection card
Endpoint CRUD SHALL be available via the management API and the UI, including a copy-paste connection card in the UI
(URL + auth instructions per client type).

#### Scenario: Connection card shows the URL and client instructions
- **WHEN** an admin opens an endpoint's detail page
- **THEN** the page shows the endpoint URL `<public base>/{endpoint_name}/mcp` with a copy button and connection
  instructions for claude.ai and for API-key clients

### Requirement: EP-8 Rename requires force
Renaming an endpoint changes its public URL and breaks every connected client. Renames MUST be rejected unless the
request carries an explicit `force` flag (mirror of [UPS-5](../upstreams/spec.md)); the rejection message
spells out the consequence, and the UI offers the rename only in its danger zone with an explicit `force` checkbox.

#### Scenario: Rename without force is refused
- **WHEN** an admin calls `POST /api/v1/endpoints/main:rename?new_name=other` without `force=true`
- **THEN** the API answers `409 Conflict` explaining that the public URL changes and connected clients break
- **AND** the endpoint keeps its name

#### Scenario: Rename with force succeeds
- **WHEN** an admin repeats the rename with `force=true`
- **THEN** the endpoint is served at `/other/mcp` and `/main/mcp` answers 404

#### Scenario: Name change through PUT is refused
- **WHEN** an admin sends `PUT /api/v1/endpoints/main` with a body whose `name` is `other`
- **THEN** the API rejects the request and points at the rename operation

### Requirement: EP-9 Request size limit
`POST /{endpoint_name}/mcp` MUST reject a request whose declared `Content-Length` exceeds 4 MiB with `413 Payload Too
Large`, before the body is parsed or any database work is done.

#### Scenario: Oversized request is rejected early
- **WHEN** a client posts to `/main/mcp` with `Content-Length` greater than 4 MiB
- **THEN** the gateway answers 413 without authenticating the caller

### Requirement: EP-10 default profile
The `default` profile SHALL be a passthrough: no tool transformation; any auth mode allowed (per
[EP-3](../endpoints/spec.md)).

#### Scenario: Annotations pass through unchanged
- **GIVEN** a `default`-profile endpoint over an upstream tool without `readOnlyHint`
- **WHEN** a client lists tools
- **THEN** the tool is presented without `readOnlyHint: true`

### Requirement: EP-11 claude profile
The `claude` profile (claude.ai remote MCP connector):

- MUST have `oauth` in `auth_modes` (validated on endpoint write, see EP-15);
- SHALL pass tools through untransformed;
- guarantees the OAuth discovery surface claude.ai needs: dynamic client registration, PKCE, `.well-known` metadata
  ([OAuth server](../auth/spec.md)).

#### Scenario: claude endpoint without oauth is rejected
- **WHEN** an admin writes a `claude`-profile endpoint with `auth_modes: [api_key]`
- **THEN** the management API rejects the write with a validation error

#### Scenario: claude endpoint tools are passthrough
- **GIVEN** a `claude`-profile endpoint
- **WHEN** a client lists tools
- **THEN** each tool's annotations are the upstream annotations with only the bundle's per-tool overrides applied

### Requirement: EP-12 chatgpt profile re-annotation
The `chatgpt` profile (ChatGPT connector, which restricts/behaves differently toward write tools):

- **re-annotates write tools as read-safe**: every served tool's annotations SHALL be rewritten so the client treats it
  as read-only — `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint` preserved. The tools **still perform
  their real (write) operations upstream**; only the presented annotations change. This is the user-chosen semantic:
  expose everything, shaped to what the client accepts.
- The UI MUST display a clear warning on chatgpt-profile endpoints that annotations no longer reflect true tool
  behavior, and the audit log records calls normally so writes remain traceable.
- Explicit per-tool overrides ([BND-15](../bundles/spec.md)) MUST win over the profile rewrite.

#### Scenario: Every tool is presented as read-safe
- **GIVEN** a `chatgpt`-profile endpoint over a tool annotated `{"readOnlyHint": false, "destructiveHint": true,
  "openWorldHint": true}`
- **WHEN** a client lists tools
- **THEN** the tool is presented with `readOnlyHint: true`, `destructiveHint: false` and `openWorldHint: true`

#### Scenario: Call still performs the real operation and is audited
- **GIVEN** a `chatgpt`-profile endpoint
- **WHEN** a client calls a write tool
- **THEN** the upstream tool runs as usual and the call is recorded in the audit log

#### Scenario: UI warns on a chatgpt endpoint
- **WHEN** an admin selects the `chatgpt` profile for an endpoint
- **THEN** the UI shows a warning that annotations no longer reflect true tool behavior

### Requirement: EP-13 Where profile transforms apply
Profile transforms SHALL be applied as a pluggable stage of the endpoint's tool pipeline at the endpoint layer — after
bundle curation decides which tools are served and before per-tool annotation overrides are merged
([BND-15](../bundles/spec.md)) — and the output of that pipeline SHALL back both `tools/list` and
`tools/call` validation, so a call is checked against exactly the transformed tool the list presented.

#### Scenario: List and call see the same transformed tool
- **GIVEN** a `chatgpt`-profile endpoint and a tool disabled in the bundle
- **WHEN** a client lists tools and calls the disabled tool
- **THEN** the disabled tool is absent from the list and rejected on call, and every listed tool carries the profile's
  annotations

#### Scenario: Overrides are applied after the profile stage
- **GIVEN** a `chatgpt`-profile endpoint and a tool with the annotation override `{"readOnlyHint": false}`
- **WHEN** a client lists tools
- **THEN** the tool's `readOnlyHint` is `false` and its `destructiveHint` is `false`

#### Scenario: A profile that hides a tool hides it from calls too
- **GIVEN** an endpoint whose profile's transform drops a tool from the served set
- **WHEN** a client calls that tool by its presented name
- **THEN** the gateway answers the same unknown-tool error as for a disabled tool and contacts no upstream

### Requirement: EP-14 Profiles are code presets listed by the API
Adding a new profile SHALL be a code change that implements one small interface — the profile's name, description and
optional warning, the auth-mode constraint it enforces on endpoint writes (EP-15), and the transform it applies to
served tools — and registers it in the gateway's single profile catalogue; no other part of the gateway branches on a
profile's name. The management API MUST list the registered profiles (name, description, and an optional warning) so
the UI stays data-driven.

#### Scenario: Profiles are listed
- **WHEN** an admin requests the profile listing from the management API
- **THEN** the response lists `default`, `claude` and `chatgpt` with descriptions, and `chatgpt` carries a warning

#### Scenario: A registered profile is used everywhere
- **GIVEN** a profile registered in the catalogue with an auth-mode constraint and a tool transform
- **WHEN** an admin lists profiles, writes an endpoint with that profile, and a client lists and calls tools on it
- **THEN** the profile is listed, endpoint writes violating its constraint are rejected with a validation error naming
  the profile, and its transform is applied to the served tools

### Requirement: EP-15 Profile × auth-mode validation matrix
The following matrix MUST be enforced on endpoint create/update:

| Profile | Allowed `auth_modes` |
|---|---|
| `claude` | exactly `[oauth]` |
| `chatgpt` | must include `oauth` or `api_key`; bare `[none]` rejected |
| `default` | any valid combination per [EP-3](../endpoints/spec.md) |

#### Scenario: claude requires exactly oauth
- **WHEN** an admin writes a `claude`-profile endpoint with `auth_modes: [oauth, api_key]`
- **THEN** the write is rejected with a validation error naming the profile rule

#### Scenario: chatgpt rejects an open endpoint
- **WHEN** an admin writes a `chatgpt`-profile endpoint with `auth_modes: [none]` and `allow_unauthenticated: true`
- **THEN** the write is rejected with a validation error

#### Scenario: default accepts any valid combination
- **WHEN** an admin writes a `default`-profile endpoint with `auth_modes: [oauth, api_key]`
- **THEN** the write succeeds

### Requirement: EP-16 Endpoint and per-client limits
Each endpoint SHALL support two independent optional limits (`rate_limit` json):

- **endpoint limit**: max requests per window across all callers;
- **per-client limit**: max requests per window per caller, keyed by resolved identity
  ([EP-6](../endpoints/spec.md)) — user `sub` or API key id — falling back to client IP for `none`-auth endpoints.

#### Scenario: Endpoint limit caps all callers together
- **GIVEN** an endpoint with an endpoint limit of 2 calls per window
- **WHEN** two different callers make three `tools/call` requests in one window
- **THEN** the third request is rejected with 429

#### Scenario: Per-client limit isolates callers
- **GIVEN** an endpoint with a per-client limit of 1 call per window
- **WHEN** caller A makes two calls and caller B one call in the same window
- **THEN** A's second call is rejected and B's call is admitted

### Requirement: EP-17 Shared counters in Redis
Enforcement MUST use Redis (Valkey) shared by all replicas — a fixed-window counter (`INCR`+`EXPIRE`, bucketed by
the store's server time). No in-process counters ([ARC-9](../architecture/spec.md)).

#### Scenario: Two replicas share one window
- **GIVEN** two gateway instances using the same Valkey and an endpoint limit of 1 call per window
- **WHEN** one call reaches each instance in the same window
- **THEN** the second call is rejected

### Requirement: EP-18 429 with Retry-After, not audited
Exceeding a limit MUST return HTTP 429 with `Retry-After`; rejections SHALL be counted in the gateway's in-process
rejection counter but are NOT audit records (audit is tool calls only).

#### Scenario: Limit exceeded
- **WHEN** a caller exceeds a configured limit
- **THEN** the gateway answers HTTP 429 with a JSON-RPC error and a `Retry-After` header giving the seconds until the
  window rolls over
- **AND** the rejection counter increases and no audit record is written

### Requirement: EP-19 Which methods count
Limits MUST apply to MCP `tools/call` requests; `initialize`, `tools/list` and `server/discover` SHALL be exempt by
default, with a per-endpoint flag (`include_initialize_list`) to include them.

#### Scenario: Startup methods are exempt by default
- **GIVEN** an endpoint with a limit of 1 call per window and `include_initialize_list` unset
- **WHEN** a client sends `initialize`, `tools/list` and then one `tools/call`
- **THEN** all three requests are admitted

#### Scenario: Endpoint opts startup methods in
- **GIVEN** the same endpoint with `include_initialize_list: true`
- **WHEN** a client sends `initialize` and then `tools/list` in one window
- **THEN** the `tools/list` request is rejected with 429

### Requirement: EP-20 Authentication-failure limiter
Authentication failures MUST be rate-limited separately (fixed gateway-wide policy keyed by client IP, Redis-backed) to
slow credential scanning — carry-over of metamcp's auth rate limiter — on the MCP edge and the OAuth token endpoint. A
locked-out client's standing MUST be checked **before** its credential is evaluated, so a lockout refuses correct
credentials too rather than only shaping the error it gets.

#### Scenario: Repeated bad credentials lock the client out
- **GIVEN** the auth-failure limit is N per window
- **WHEN** a client presents bad credentials more than N times in one window
- **THEN** further attempts are answered 429 with `Retry-After` instead of 401

#### Scenario: Lockout refuses a correct credential
- **GIVEN** a locked-out client IP
- **WHEN** it presents a valid credential
- **THEN** the gateway answers 429 without evaluating the credential

### Requirement: EP-21 Redis-outage stance
Traffic limits (EP-16) MUST **fail open** when the store is unreachable, with a WARN log and an in-process counter
increment (an endpoint may opt into fail-closed via its `rate_limit` config, `fail_closed`); the auth-failure limiter
(EP-20) MUST also fail open, increasing the same counter — availability over throttling, never silently.

#### Scenario: Store outage fails open
- **GIVEN** an endpoint with a rate limit and an unreachable Valkey
- **WHEN** a client calls a tool
- **THEN** the call is admitted, a WARN log is written and the fail-open counter increases

#### Scenario: Endpoint opted into fail-closed
- **GIVEN** the same outage and an endpoint whose `rate_limit` has `fail_closed: true`
- **WHEN** a client calls a tool
- **THEN** the call is rejected with 429

### Requirement: EP-22 Client IP and time source
Client IP for the `none`-auth fallback MUST derive from the trusted-proxy policy ([DEP-2](../deployment/spec.md));
windows MUST use the store's server time ([ARC-15](../architecture/spec.md)).

#### Scenario: Forwarded header only from a trusted proxy
- **GIVEN** a request whose socket peer is not a configured trusted proxy and that carries `X-Forwarded-For`
- **WHEN** the per-client bucket is chosen for a `none`-auth endpoint
- **THEN** the socket peer address is used, not the forwarded address

## Out of scope

### Endpoints

- Custom domains per endpoint (operator's reverse proxy concern).

### Endpoint profiles

- User-defined/scriptable profiles (revisit if built-ins prove insufficient).
- ChatGPT's `search`/`fetch` deep-research connector contract (dropped in scoping; can become a fourth profile later
  without structural change).

### Rate limiting

- Billing/credit enforcement (that is the application layer's metering hook — [protocol](../protocol/spec.md)).
- Global (cross-endpoint) traffic shaping.

## Notes

### Endpoints

Origin: improvement over metamcp (1 endpoint ↔ 1 namespace; bundlemcp: N endpoints per bundle). Prior art:
`../metamcp/apps/backend/src/routers/public-metamcp/`, `endpoints` table.

Resolved: `GET /{endpoint_name}/mcp` is required (EP-1a) for handshake-era sessions — the full-bidirectional decision
depends on it; it answers 405 for requests without a session, as MCP 2026-07-28 prescribes.

### Endpoint profiles

Origin: new — the reason bundlemcp supports N endpoints per bundle.

Open question: verify against current ChatGPT connector behavior which annotation set it enforces, and adjust EP-12's
exact rewrite map accordingly.

### Rate limiting

Origin: improvement (metamcp had per-process counters). Prior art:
`../metamcp/apps/backend/src/middleware/rate-limit.middleware.ts`, `lib/rate-limit.ts`. Rationale and the choice of the
fixed-window algorithm: [ADR-0018](../../../docs/adr/0018-rate-limiting.md). A per-client limit keys on any resolved
identity first and falls back to the client IP whenever no identity is present.
