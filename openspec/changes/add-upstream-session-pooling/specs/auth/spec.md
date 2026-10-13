## MODIFIED Requirements

### Requirement: AUTH-31 Forwarded headers never cross callers
An upstream connection carrying user A's forwarded authorization MUST never serve user B's request
([sessions](../../../../specs/sessions/spec.md)). Upstream sessions of a server that forwards caller
headers SHALL be keyed by an identity key that incorporates a hash of the **forwarded header values**, not just the
resolved `sub`: the same user presenting different credentials (e.g. on two endpoints) gets distinct upstream sessions,
and a pooled session is reused only for a request whose identity key matches the one it was opened with. Header values
themselves are never stored; only the hash is.

#### Scenario: Two callers, two connections
- **WHEN** users A and B call the same tool of a server that forwards `authorization`, on the same replica
- **THEN** each upstream request carries only its own caller's forwarded header value

#### Scenario: Same user, different credentials
- **WHEN** one user calls a tool of a server that forwards `authorization` through two endpoints with different tokens
- **THEN** the two calls run on two distinct upstream sessions

#### Scenario: Matching identity key reuses the session
- **WHEN** the same caller with the same forwarded header values calls the server twice on one replica
- **THEN** the second call reuses the first call's pooled upstream session
