## MODIFIED Requirements

### Requirement: PROT-7 Logging relay
Upstream `notifications/message` (logging) SHALL be relayed to the client when it asked for them, at or above the level
it asked for: a handshake client enables logging with `logging/setLevel`, which is stored on its session, applied to
every later upstream request on that session, and sent as `logging/setLevel` to each enabled member that advertises
logging, on the upstream session bound to the client's session; a modern client sets
`_meta["io.modelcontextprotocol/logLevel"]` per request (PROT-20). For a handshake client a log message is delivered on
the call's response stream when the call is streamed, otherwise on its GET stream; a log message a member sends
**between** calls on an upstream session bound to the client's session is delivered on the GET stream, from whichever
replica holds it.

#### Scenario: Handshake client after setLevel
- **WHEN** a handshake client sends `logging/setLevel` `info`, holds a GET stream and calls a tool that logs at `info`
- **THEN** a `notifications/message` with the upstream's log arrives on the GET stream

#### Scenario: setLevel fans out to members
- **WHEN** a handshake client sends `logging/setLevel` `warning` on a bundle with members `echo` (advertises logging)
  and `calc` (does not)
- **THEN** `echo` receives `logging/setLevel` `warning` on the client's bound upstream session and `calc` receives
  nothing

#### Scenario: Log pushed between calls
- **GIVEN** a handshake client set level `info` and holds a GET stream
- **WHEN** member `echo` sends a `notifications/message` at `error` while no call is in flight
- **THEN** the message arrives on the client's GET stream

#### Scenario: Unknown level
- **WHEN** a client sends `logging/setLevel` with level `loud`
- **THEN** the gateway answers `-32602`

### Requirement: PROT-17 subscriptions/listen
A modern client SHALL open change notifications with one long-lived POST whose response stream first carries
`notifications/subscriptions/acknowledged` echoing the subset of the filter the gateway honours, then only the
notification types acknowledged, each tagged with `_meta["io.modelcontextprotocol/subscriptionId"]` = the request id.
The gateway honours `toolsListChanged` (BND-7 invalidations and member changes per PROT-10, delivered cross-replica),
`promptsListChanged` and `resourcesListChanged` for the bundle's own prompts and resources
([BND-28](../bundles/spec.md)) and for its members' (PROT-10), and
`resourceSubscriptions`: `notifications/resources/updated` for each URI the filter names, relayed from the owning member
over a pooled upstream session (PROT-23). The stream sends SSE keep-alive comments, ends with a completion result on
graceful shutdown, and is closed by the client to unsubscribe, which also ends the upstream resource subscriptions it
held. GET and DELETE on the endpoint without an `Mcp-Session-Id` answer 405
([EP-1](../endpoints/spec.md)).

#### Scenario: Acknowledge and relay
- **WHEN** a modern client opens `subscriptions/listen` asking for `toolsListChanged` and `resourceSubscriptions`, and
  the bundle's curation then changes
- **THEN** the first event acknowledges both
- **AND** a `notifications/tools/list_changed` tagged with the subscription id follows

#### Scenario: Change through another replica
- **WHEN** the listen stream is held by replica B and the bundle is changed through replica A
- **THEN** the stream on B receives the notification

#### Scenario: Resource update for a subscribed URI
- **WHEN** a modern client listens with `resourceSubscriptions` naming `file:///report` and the owning member updates it
- **THEN** the stream receives `notifications/resources/updated` for `file:///report` tagged with the subscription id

#### Scenario: Closing the stream unsubscribes upstream
- **WHEN** the client closes that listen stream
- **THEN** the gateway unsubscribes from `file:///report` upstream

## ADDED Requirements

### Requirement: PROT-10 Upstream list changes
Upstream `notifications/tools/list_changed`, `notifications/prompts/list_changed` and
`notifications/resources/list_changed`, received on a pooled upstream session during or between calls, SHALL trigger
re-discovery of that server ([UPS-17](../upstreams/spec.md)) and be propagated to the connected
clients of every bundle the server is an enabled member of, per [BND-7](../bundles/spec.md): on the GET
stream for handshake clients, on the `subscriptions/listen` stream for modern clients (PROT-17). The same change
announced to several replicas' sessions MUST trigger one re-discovery, not one per replica.

#### Scenario: Tool list change between calls
- **GIVEN** a handshake client holds a GET stream on an endpoint whose bundle contains server `echo`
- **WHEN** `echo` sends `notifications/tools/list_changed` while no call is in flight
- **THEN** `echo` is re-discovered and the client's GET stream receives `notifications/tools/list_changed`

#### Scenario: Member prompt list change reaches a modern listener
- **WHEN** a modern client listens with `promptsListChanged` and a member sends `notifications/prompts/list_changed`
- **THEN** the client's listen stream receives `notifications/prompts/list_changed` tagged with its subscription id

#### Scenario: One re-discovery for several replicas
- **GIVEN** replicas A and B each hold a pooled session to `echo`
- **WHEN** `echo` announces one tool list change on both sessions
- **THEN** discovery for `echo` runs once

### Requirement: PROT-23 Resource subscriptions
A handshake client's `resources/subscribe` for a member resource SHALL be relayed to the owning member on an upstream
session bound to the client's session, and the subscription recorded in the RESP store; each
`notifications/resources/updated` the member sends for that URI, during or between calls, SHALL be delivered on the
client's GET stream, from whichever replica holds it. `resources/unsubscribe`, ending the session, or rebinding to a new
upstream session (SES-7) MUST unsubscribe or re-subscribe upstream accordingly.

#### Scenario: Update pushed between calls
- **GIVEN** a handshake client subscribed to `file:///report` owned by member `docs` and holds a GET stream
- **WHEN** `docs` sends `notifications/resources/updated` for `file:///report` while no call is in flight
- **THEN** the client's GET stream receives that notification

#### Scenario: Unsubscribe stops updates
- **WHEN** the client sends `resources/unsubscribe` for the URI and `docs` later updates it
- **THEN** the gateway has unsubscribed upstream and nothing is delivered to the client

#### Scenario: Subscription survives an upstream session loss
- **WHEN** the bound upstream session is re-initialized after a 404
- **THEN** the gateway re-subscribes to `file:///report` on the new upstream session
