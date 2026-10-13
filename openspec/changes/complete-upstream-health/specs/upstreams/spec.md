## MODIFIED Requirements

### Requirement: UPS-23 Periodic refresh
Periodic refresh: every `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL` seconds (default 1800; `0` disables it) the gateway MUST
re-run discovery for every registered server, one server at a time. Only one replica refreshes per interval: the run
takes a shared, self-expiring lease in Valkey, and a replica that finds it held skips that tick. Each run is an
ordinary discovery, so a changed tool set is announced (BND-7), and failures count toward `health_status` like any other
probe ([UPS-4](../../../../specs/upstreams/spec.md)): because the failure count is shared by every replica, an
upstream that stays unreachable is marked `error` after `server_error_attempts` refreshes instead of staying `unknown`,
whichever replica ran each sweep. One server's failure never stops the run for the rest, and every discovery probe is
bounded (60 s) so a hanging upstream fails instead of stalling the run. This covers the upstreams the other triggers
miss: one that was unreachable when it was registered, and one whose tools change while no call is open to it.
Per-call upstream connections ([ADR-0012](../../../../../docs/adr/0012-per-call-upstream-connections.md)) never
receive a `list_changed` sent between calls ([PROT-10](../../../../specs/protocol/spec.md) residual).
Rationale and the alternatives weighed: [ADR-0038](../../../../../docs/adr/0038-periodic-tool-refresh.md).

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

## ADDED Requirements

### Requirement: UPS-9 Background health polling
The gateway SHALL offer optional background health polling, controlled by the runtime config keys
`health_poll_enabled` (default `false`) and `health_poll_interval` (seconds, default 300). When enabled, every interval
the gateway SHALL connect to each registered server that has something to connect with, bounded in time, and count the
result toward `health_status` like any other probe (UPS-4), so health stays fresh for servers receiving no traffic.
Only one replica polls per interval. Polling never changes the cached tools.

#### Scenario: Polling is off by default
- **WHEN** the gateway runs with no stored value for `health_poll_enabled`
- **THEN** no upstream is contacted for health polling

#### Scenario: Polling marks an idle, unreachable server as failing
- **GIVEN** `health_poll_enabled` is `true` and `server_error_attempts` is `3`
- **WHEN** a server receiving no traffic is unreachable for three consecutive polls
- **THEN** its `health_status` is `error`

#### Scenario: One replica polls per interval
- **WHEN** two replicas reach the same polling tick
- **THEN** each server is polled once in that interval

#### Scenario: An unconnected OAuth upstream is not polled
- **WHEN** polling is enabled and an `upstream_oauth` server has no connected account
- **THEN** that server is not contacted and its failure count is unchanged
