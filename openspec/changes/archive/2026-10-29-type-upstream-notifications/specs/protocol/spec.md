## MODIFIED Requirements

### Requirement: PROT-7 Logging relay
Upstream `notifications/message` (logging) SHALL be relayed to the client when it asked for them, at or above the level
it asked for: a handshake client enables logging with `logging/setLevel`, which is stored on its session, applied to
every later upstream request on that session, and sent as `logging/setLevel` to each enabled member that advertises
logging, on the upstream session bound to the client's session; a modern client sets
`_meta["io.modelcontextprotocol/logLevel"]` per request (PROT-20). For a handshake client a log message is delivered on
the call's response stream when the call is streamed, otherwise on its GET stream; a log message a member sends
**between** calls on an upstream session bound to the client's session is delivered on the GET stream, from whichever
replica holds it. A log message relayed between calls carries the member's `level`, `logger` and `data`; the member's
own `_meta` MUST NOT be forwarded, since it describes the member's hop to the gateway, not the client's.

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

#### Scenario: A member's meta is not relayed with its log
- **GIVEN** a handshake client set level `info` and holds a GET stream
- **WHEN** member `echo` sends, while no call is in flight, a `notifications/message` at `error` with logger `db`, data
  `"lost"` and a `_meta` of its own
- **THEN** the message on the client's GET stream has level `error`, logger `db` and data `"lost"`, and no `_meta` from
  `echo`

#### Scenario: Unknown level
- **WHEN** a client sends `logging/setLevel` with level `loud`
- **THEN** the gateway answers `-32602`

### Requirement: PROT-23 Resource subscriptions
A handshake client's `resources/subscribe` for a member resource SHALL be relayed to the owning member on an upstream
session bound to the client's session, and the subscription recorded in the RESP store; each
`notifications/resources/updated` the member sends for that URI, during or between calls, SHALL be delivered on the
client's GET stream, from whichever replica holds it. `resources/unsubscribe`, ending the session, or rebinding to a new
upstream session (SES-7) MUST unsubscribe or re-subscribe upstream accordingly.

How the gateway subscribes upstream follows the era the upstream session negotiated
([PROT-21](../protocol/spec.md)): a handshake-era member is sent `resources/subscribe` and `resources/unsubscribe`; a
modern member, which has no such methods, has the URI added to or removed from the `resourceSubscriptions` of the
gateway's standing `subscriptions/listen` stream to it. Either way the client sees the same subscription. A relayed
update carries the URI the member named; the member's own `_meta` MUST NOT be forwarded.

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

#### Scenario: A modern member is watched through its listen stream
- **GIVEN** member `docs` negotiated the 2026-07-28 revision
- **WHEN** a handshake client subscribes to `file:///report`
- **THEN** `docs` receives no `resources/subscribe`
- **AND** the gateway's `subscriptions/listen` stream to `docs` names `file:///report` in its `resourceSubscriptions`

#### Scenario: A member's meta is not relayed with an update
- **GIVEN** a handshake client subscribed to `file:///report` owned by member `docs` and holds a GET stream
- **WHEN** `docs` sends `notifications/resources/updated` for `file:///report` with a `_meta` of its own
- **THEN** the client's GET stream receives `notifications/resources/updated` for `file:///report` without that `_meta`

## ADDED Requirements

### Requirement: PROT-30 Refetch after a re-opened member listen stream
When the gateway's standing `subscriptions/listen` stream to a modern member ends, the gateway SHALL re-open it, and
once the member acknowledges the re-opened stream it SHALL treat every list it listens for as changed (PROT-10,
including its one re-discovery across replicas) and relay `notifications/resources/updated` for every URI the stream
watches. The protocol replays nothing, so a change made while the stream was down is otherwise never heard.

#### Scenario: A list change made while the stream was down
- **GIVEN** the gateway listens to member `echo`, which advertises `tools` with `listChanged`, and a handshake client
  holds a GET stream on a bundle containing `echo`
- **WHEN** `echo`'s listen stream is lost, `echo` adds a tool, and the gateway re-opens the stream
- **THEN** `echo` is re-discovered once and the client's GET stream receives `notifications/tools/list_changed`

#### Scenario: A watched resource after a re-open
- **GIVEN** a client is subscribed to `file:///report` owned by modern member `docs`
- **WHEN** the gateway's listen stream to `docs` is lost and re-opened
- **THEN** the client receives `notifications/resources/updated` for `file:///report`

#### Scenario: The first open refetches nothing
- **WHEN** the gateway opens its first listen stream on a new upstream session to `echo`
- **THEN** no list change and no resource update is relayed until `echo` sends one

#### Scenario: A filter change is not a loss
- **WHEN** the gateway re-opens the stream to `docs` only because a client subscribed to another URI
- **THEN** no list change and no resource update is relayed for the URIs already watched
