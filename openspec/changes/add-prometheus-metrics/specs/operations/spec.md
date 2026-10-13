## ADDED Requirements

### Requirement: OPS-9 Prometheus metrics
The gateway SHALL serve Prometheus text-format metrics at `/metrics`, authenticated like the management API (a service
API key or an admin session), exposing at
minimum: tool-call count and duration histogram (labels endpoint, server, status), active sessions, upstream in-flight
calls and failures per server, rate-limit rejections, metering denies, audit queue depth, and Postgres and Valkey
health. Each replica SHALL export its own values; operators scrape every replica.

#### Scenario: Tool call is counted and timed
- **GIVEN** a successful `tools/call` of `echo__say` on endpoint `main`
- **WHEN** `/metrics` is scraped with a service API key
- **THEN** the tool-call counter with labels `endpoint="main"`, `server="echo"`, `status="success"` has increased by
  one and the duration histogram has one more observation under the same labels

#### Scenario: Metrics require a service key
- **WHEN** `/metrics` is requested without credentials
- **THEN** the response is 401 and carries no metric values

#### Scenario: Endpoint keys cannot read metrics
- **WHEN** `/metrics` is requested with an endpoint-kind API key
- **THEN** the response is 403 and carries no metric values

#### Scenario: Store health is exported
- **GIVEN** Valkey cannot be reached
- **WHEN** `/metrics` is scraped
- **THEN** the store-health gauge for `valkey` reads 0 and the one for `postgres` reads 1

#### Scenario: Each replica exports its own counters
- **GIVEN** two replicas behind one load balancer
- **WHEN** a tool call is served by replica A only
- **THEN** replica A's tool-call counter increases and replica B's does not, so summing the scrapes of both counts the
  call exactly once

#### Scenario: Metering denies are counted
- **WHEN** the metering hook denies a call on endpoint `main`
- **THEN** the metering-deny counter for `endpoint="main"` increases by one

#### Scenario: Metrics can be switched off
- **GIVEN** `BUNDLEMCP_METRICS_ENABLED=false`
- **WHEN** `/metrics` is requested
- **THEN** the response is 404

### Requirement: OPS-11 Degraded-response visibility
When an endpoint serves a `tools/list` that includes a member upstream whose health is `error`, so the listed tools are
the last-known cache rather than a fresh view, the gateway MUST increment a dedicated degraded-response metric
(labels endpoint, server) and write a WARN log naming the endpoint and the server — never silently.

#### Scenario: Unhealthy member makes the listing degraded
- **GIVEN** bundle `b` with members `echo` (health `ok`) and `weather` (health `error`), exposed on endpoint `main`
- **WHEN** a client calls `tools/list` on `main`
- **THEN** the response still lists the cached tools of both members
- **AND** the degraded-`tools/list` counter for `endpoint="main"`, `server="weather"` increases by one
- **AND** a WARN log record names endpoint `main` and server `weather`

#### Scenario: Healthy listing is not degraded
- **GIVEN** every member of the bundle has health `ok`
- **WHEN** a client calls `tools/list`
- **THEN** the degraded-`tools/list` counter does not change and no WARN is written
