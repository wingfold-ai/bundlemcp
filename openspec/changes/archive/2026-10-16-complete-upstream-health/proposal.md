# Proposal

## Why

`health_status` is what an admin and an operator look at to see whether an upstream works, and today it is unreliable.
The consecutive-failure count lives in a per-process dict inside `DiscoveryService`, which breaks the "no in-memory-only
state a request depends on" rule: the UPS-23 periodic refresh runs on whichever replica takes the lease, so failures
spread over replicas never reach the threshold and a dead upstream registered while down stays `unknown` forever. The
threshold is the constant `DEFAULT_MAX_ATTEMPTS = 3` (`application/discovery/discovery_service.py:23`) even though the
runtime config key `server_error_attempts` exists, and failed live calls do not count at all.

## What Changes

- The failure count moves to Valkey and is shared by every replica (UPS-4).
- The threshold is read from the runtime config key `server_error_attempts` (default 3) instead of a constant (UPS-4).
- Live `tools/call` requests count too: an upstream that cannot be reached counts as a failure, any MCP response —
  including a tool error — as a success that heals the server (UPS-4).
- UPS-23 sweeps on different replicas therefore add up, and an upstream that stays down is marked `error` after
  `server_error_attempts` sweeps (UPS-23).
- Background health polling (UPS-9) is retired, not built; see the decision below.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `upstreams`: UPS-4 (configurable threshold, shared count, live calls count).
- `upstreams`: UPS-23 (an upstream that stays unreachable is marked `error` after that many refreshes).

## Decision: UPS-9 is retired

The original spec asked for optional background health polling so health stays fresh for servers without traffic.
UPS-23's periodic refresh already re-probes every server (every 30 minutes by default), and with the shared count of
this change it also drives `health_status`, so polling would only make health fresher at the cost of upstream traffic
that ADR-0043 ("contact upstreams only with a reason") argues against. The maintainers chose to retire it: no delta is
written, nothing is REMOVED because UPS-9 was never in the main spec, and the ID stays unused.

## Impact

- **Code:** a new live-state contract for the failure streak (`application/contracts/live_state/`) with a Valkey
  adapter and an in-memory fake; `DiscoveryService` reads the threshold from `RuntimeConfig`; a health reporter in
  `application/discovery/` used by discovery and by the tool-call settlement in `api/mcp/tool_call/`.
- **Config:** `server_error_attempts` starts to take effect.
- **Data:** no Postgres migration. New Valkey keys, self-expiring.
- **Docs:** `docs/manage/servers.md` (health), `docs/self-hosting/configuration.md`, and
  `docs/self-hosting/operations.md`.
- **Related changes:** [add-upstream-session-pooling](../add-upstream-session-pooling/proposal.md) (SES-7: repeated
  re-initialize failures feed `health_status`) should report through the health reporter added here.
  [add-prometheus-metrics](../2026-10-16-add-prometheus-metrics/proposal.md) may export health transitions as a metric;
  not required here.
- No ADR: the change brings the implementation in line with the existing state-model rule (ARC, ADR-0004).
