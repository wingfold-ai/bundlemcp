## MODIFIED Requirements

### Requirement: EP-18 429 with Retry-After, not audited
Exceeding a limit MUST return HTTP 429 with `Retry-After`; rejections SHALL be counted in the gateway's exported
metrics ([OPS-9](../../../../specs/operations/spec.md), labelled by endpoint and by which limit — endpoint-wide or
per-client — was exceeded) but are NOT audit records (audit is tool calls only).

#### Scenario: Limit exceeded
- **WHEN** a caller exceeds a configured limit
- **THEN** the gateway answers HTTP 429 with a JSON-RPC error and a `Retry-After` header giving the seconds until the
  window rolls over
- **AND** the rejection counter increases and no audit record is written

#### Scenario: Rejection is visible in exported metrics
- **GIVEN** endpoint `main` with a per-client limit of 1 call per window
- **WHEN** one client sends two `tools/call` requests in one window and `/metrics` is then scraped
- **THEN** the rate-limit rejection counter for `endpoint="main"`, `limit="client"` reads one more than before

### Requirement: EP-21 Redis-outage stance
Traffic limits (EP-16) MUST **fail open** when the store is unreachable, with a WARN log and an increment of the
exported traffic-limiter fail-open metric (an endpoint may opt into fail-closed via its `rate_limit` config,
`fail_closed`); the auth-failure limiter (EP-20) MUST also fail open, but SHALL raise a dedicated alarm metric of its
own, distinct from the traffic limiter's, plus a WARN log — availability over throttling, never silently.

#### Scenario: Store outage fails open
- **GIVEN** an endpoint with a rate limit and an unreachable Valkey
- **WHEN** a client calls a tool
- **THEN** the call is admitted, a WARN log is written and the traffic-limiter fail-open metric increases

#### Scenario: Endpoint opted into fail-closed
- **GIVEN** the same outage and an endpoint whose `rate_limit` has `fail_closed: true`
- **WHEN** a client calls a tool
- **THEN** the call is rejected with 429

#### Scenario: Auth-failure limiter fails open with its own alarm
- **GIVEN** an unreachable Valkey
- **WHEN** a client presents a bad credential on an MCP endpoint
- **THEN** the request is answered 401 rather than 429, a WARN log is written, the auth-limiter fail-open alarm metric
  increases, and the traffic-limiter fail-open metric does not change
