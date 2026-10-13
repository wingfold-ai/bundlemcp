## MODIFIED Requirements

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
