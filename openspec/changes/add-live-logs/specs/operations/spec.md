## ADDED Requirements

### Requirement: OPS-14 Capped cross-replica log buffer
Gateway log events (the structured events of [OPS-8](../../../../specs/operations/spec.md) at or above a
configurable level threshold, plus connection and session lifecycle events) SHALL be published to a capped stream in
the RESP store (approximately the newest 10,000 entries), shared by all replicas. Publishing MUST NOT block or fail the
request that logged the event.

#### Scenario: Events from two replicas land in one buffer
- **GIVEN** two gateway replicas sharing one RESP store
- **WHEN** each replica logs an event at or above the threshold
- **THEN** both events are in the buffer, each tagged with the replica that wrote it

#### Scenario: Events below the threshold are not published
- **GIVEN** the live-log threshold is `WARNING`
- **WHEN** the gateway logs an `INFO` event
- **THEN** the event is written to the process log but not to the buffer

#### Scenario: The buffer stays capped
- **WHEN** more than 10,000 events are published
- **THEN** the buffer holds approximately the newest 10,000 and the oldest are dropped

#### Scenario: A store outage does not fail requests
- **GIVEN** the RESP store is unreachable
- **WHEN** a request logs an event
- **THEN** the request completes as usual and the event is only written to the process log

### Requirement: OPS-15 Live log page
The admin UI SHALL show a page that streams new buffer entries from the management API (a server-push stream,
admin-authenticated) with pause and resume, a level filter, and free-text, upstream and endpoint filters. Resuming
after a pause or a dropped connection continues from the last entry shown, as long as it is still in the buffer.

#### Scenario: New entries appear without reload
- **GIVEN** an admin has the live log page open
- **WHEN** the gateway logs an event at or above the threshold
- **THEN** it appears on the page within a few seconds, without a reload

#### Scenario: Filters narrow the stream
- **WHEN** the admin filters by endpoint `b1-api` and level `ERROR`
- **THEN** only entries for that endpoint at `ERROR` or above are shown

#### Scenario: Resume continues where the page paused
- **GIVEN** the admin paused the stream and three events were logged since
- **WHEN** the admin resumes
- **THEN** the three events are shown in order, without duplicates

#### Scenario: Non-admins are refused
- **WHEN** the log stream is requested without an admin session or service API key
- **THEN** the request is refused as unauthenticated

### Requirement: OPS-16 The buffer is ephemeral
The buffer SHALL be best-effort and ephemeral: losing the RESP store's data clears it, which is acceptable by design.
Durable history is the audit log and the process logs collected by the container platform.

#### Scenario: Store loss empties the view
- **WHEN** the RESP store is restarted without persistence
- **THEN** the live log page shows only events logged after the restart, and the gateway keeps serving

### Requirement: OPS-17 Same redaction as process logs
The buffer MUST carry the already-redacted events of [OPS-8](../../../../specs/operations/spec.md), never raw
headers, tokens, secrets or tool arguments; whatever the process log may not contain, the buffer may not contain.

#### Scenario: A credential never reaches the buffer
- **WHEN** a request carrying an API key and an `Authorization` header is served and logged
- **THEN** no buffer entry contains the key, the header value, or the tool arguments
