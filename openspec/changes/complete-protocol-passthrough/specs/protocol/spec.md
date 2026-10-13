## MODIFIED Requirements

### Requirement: PROT-3 Cancellation
A cancellation MUST reach the upstream call it targets even when it arrives at a different replica than the one
holding the in-flight upstream request — routed via the RESP-store pub/sub keyed by routing key + request id
([SES-13](../../../../specs/sessions/spec.md)). A cancelled call SHALL end its upstream request and be
reported to the metering post-call hook with outcome `cancelled` ([PROT-26](../../../../specs/protocol/spec.md)). The
signals are:

- `notifications/cancelled` naming the request id — in the handshake era on the same session; in the modern era from
  the same caller on the same endpoint, since a modern call has no session: an in-flight modern call is addressable by
  caller, endpoint and request id, and a cancellation from any other caller never reaches it;
- the client closing the call's response stream, in the modern era (PROT-19) and for a handshake-era call streamed
  with a progress token;
- the client disconnecting while it waits for a buffered (non-streamed) handshake-era call.

#### Scenario: notifications/cancelled aborts the call
- **WHEN** a handshake-era client sends `notifications/cancelled` for request 7 while that `tools/call` is in flight
- **THEN** the call ends with a JSON-RPC error `cancelled` and the hook's `post_call` receives outcome `cancelled`

#### Scenario: Cancellation from another replica
- **WHEN** the call runs on replica A and the cancellation arrives at replica B
- **THEN** A receives the cancel signal over the store and ends the upstream call

#### Scenario: Modern notifications/cancelled
- **WHEN** a modern client has `tools/call` request 9 in flight and sends `notifications/cancelled` for request 9 in a
  separate request with the same credentials
- **THEN** the upstream call is ended and the hook's `post_call` receives outcome `cancelled`

#### Scenario: Another caller cannot cancel
- **WHEN** a different caller sends `notifications/cancelled` for request 9 on the same endpoint
- **THEN** the call continues and completes with its result

#### Scenario: Disconnect during a buffered call
- **WHEN** a handshake client calls a tool without a progress token and closes the connection before the result
- **THEN** the upstream call is ended and the hook's `post_call` receives outcome `cancelled`

### Requirement: PROT-11 Capability aggregation
The bundle's capability advertisement (the `initialize` result for handshake clients, the `server/discover` result for
modern clients) SHALL be computed without contacting any member, from the bundle's own prompts and resources and from
the per-server `capabilities` snapshot captured at discovery ([UPS-22](../../../../specs/upstreams/spec.md)) of
its enabled members, and SHALL advertise a notification only when the gateway delivers it:

- `tools` always, with `listChanged: true` — the gateway supports tools even with zero members;
- `prompts` and `resources` when the bundle owns one
  ([bundles](../../../../specs/bundles/spec.md)) or at least one member advertises
  it; each with `listChanged: true` when the bundle owns one, or when a member advertises `listChanged` for it and the
  gateway delivers members' list changes to clients;
- `resources.subscribe: true` only when at least one member supports it and the gateway delivers members'
  `notifications/resources/updated` to subscribed clients;
- `completions` when a bundle prompt offers completions or at least one member advertises it;
- `logging` when at least one member advertises it.

No `extensions` are advertised: the gateway proxies none.

#### Scenario: Zero members
- **WHEN** a client initializes against a bundle with no members and no own prompts or resources
- **THEN** the capabilities are exactly `tools` with `listChanged: true`

#### Scenario: Member capability is aggregated
- **GIVEN** the gateway delivers members' list changes and resource updates
- **WHEN** one enabled member's snapshot advertises `resources` with `listChanged` and `subscribe`
- **THEN** the advertisement includes `resources` with `listChanged: true` and `subscribe: true`

#### Scenario: Undelivered notifications are not advertised
- **GIVEN** the gateway does not deliver members' list changes or resource updates
- **WHEN** the bundle's only resource source is a member advertising `resources` with `listChanged` and `subscribe`
- **THEN** the advertisement includes `resources` without `listChanged` and without `subscribe`

#### Scenario: Own resources keep listChanged
- **GIVEN** the gateway does not deliver members' list changes
- **WHEN** the bundle owns a resource
- **THEN** the advertisement includes `resources` with `listChanged: true`

### Requirement: PROT-16 Result shaping and cache hints
Every modern result SHALL carry `resultType` (`"complete"`, or `"input_required"` per PROT-18) and the gateway's server
info in `_meta`. `tools/list`, `prompts/list`, `resources/list`, `resources/templates/list`, `resources/read` and
`server/discover` carry `ttlMs` and `cacheScope`: list results are `public` with a runtime-configurable TTL
(`list_cache_ttl_ms`, default 5 min), invalidated by `listChanged`, except that a `tools/list` containing a tool
presented to this caller only — a `__connect_account` tool ([UPS-27](../../../../specs/upstreams/spec.md)) — is
`private`; `resources/read` of a member resource forwards the upstream's hint when it gave one and is otherwise
`ttlMs: 0`, `private`, while a resource the bundle itself serves is hinted like a list. Error codes follow the modern
table: resource-not-found is `-32602` (it is `-32002` for handshake clients, and a modern upstream's `-32602` is mapped
back for them). `tools/list` order is deterministic (sorted by presented name). Handshake-era results are byte-for-byte
what they were before the modern era was added.

#### Scenario: Cacheable tools list
- **WHEN** a modern client sends `tools/list`
- **THEN** the result carries `resultType: "complete"`, `ttlMs` equal to `list_cache_ttl_ms` and `cacheScope: "public"`

#### Scenario: Per-caller tools list
- **WHEN** a modern client that has not connected its account to a `per_user` upstream-OAuth member sends `tools/list`
- **THEN** the result lists that member's `__connect_account` tool and carries `cacheScope: "private"`

#### Scenario: Resource not found
- **WHEN** a modern client reads a URI no member serves
- **THEN** the error code is `-32602`

#### Scenario: Handshake results unchanged
- **WHEN** a handshake client lists tools on the same endpoint
- **THEN** the result has no `resultType`, `ttlMs` or `cacheScope`

### Requirement: PROT-22 Adding a protocol revision
A new revision SHALL be supported by adding one dialect class (client hop) and, if the upstream SDK does not absorb it,
one adapter (upstream hop), registering the version, running the MCP conformance suite for that revision against the
compose stack, and recording an ADR. CI SHALL run the MCP conformance suite against the compose stack once per served
revision, and a failing check fails the build. Handlers, the relay, metering and audit MUST NOT need to change for a
revision that keeps the method set. The revision lists and the per-revision method sets are read from the MCP SDK's
registry (`mcp_types.version`, `mcp_types.methods`); the gateway keeps only its own decisions, such as the floor of the
handshake window.

#### Scenario: Served revisions come from the SDK
- **WHEN** the gateway starts
- **THEN** the served revisions are the SDK's revisions at or above the gateway's handshake floor

#### Scenario: Method sets come from the SDK
- **WHEN** a modern request names a method the SDK lists only for handshake revisions
- **THEN** it is answered method-not-found without a gateway-side denylist

#### Scenario: Conformance runs per revision in CI
- **WHEN** CI runs for a pull request
- **THEN** the conformance job runs the MCP conformance suite against the compose stack's `demo` endpoint once for
  every served revision, and a failing check fails the job
