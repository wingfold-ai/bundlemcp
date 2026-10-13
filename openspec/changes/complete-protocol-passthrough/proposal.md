# Proposal: complete the protocol passthrough

## Why

Four protocol-passthrough requirements hold only in part:

- **Cancellation (PROT-3).** A modern-era `notifications/cancelled` is accepted with 202 but cancels nothing: each
  stateless request gets a fresh routing key (`api/mcp/routing/adapters/stateless_adapter.py`, `uuid.uuid4().hex`), so
  the cancel is published under a key no in-flight call holds. A handshake client that disconnects while waiting for a
  buffered (non-streamed) call does not cancel it either; the upstream runs to completion.
- **Capability advertisement (PROT-11).** `resources.subscribe: true` is advertised whenever a member supports it, but
  `ResourcesSubscribeHandler` never pushes an update; members' prompt and resource `listChanged: true` is advertised
  although member list changes are not delivered. A client trusting the advertisement waits for notifications that
  never come.
- **Cache hints (PROT-16).** A `tools/list` that includes a caller's `__connect_account` tools (UPS-27) is per-caller,
  yet carries `cacheScope: "public"`, inviting a shared cache to serve one caller's list to another.
- **Conformance (PROT-22).** The spec makes the MCP conformance suite part of adding a revision; no harness exists and
  CI runs none.

## What Changes

- A modern `notifications/cancelled` from the same caller on the same endpoint cancels the named in-flight call, on any
  replica; a client disconnect cancels a buffered handshake call; both are metered as `cancelled` (PROT-3).
- `resources.subscribe` and members' prompt/resource `listChanged` are advertised only when the gateway delivers the
  corresponding notifications (PROT-11).
- A `tools/list` containing per-caller tools is `cacheScope: "private"` (PROT-16).
- A conformance-suite harness runs against the compose stack in CI for every served revision (PROT-22).

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `protocol`: MODIFIED PROT-3 (modern cancel by request id, buffered-call disconnect), PROT-11 (advertise
  only what is delivered), PROT-16 (`private` for per-caller lists), PROT-22 (conformance suite in CI).

## Impact

- **Code:** the stateless adapter derives an in-flight call key from caller, endpoint and request id; the cancelled
  notification handler publishes under it (`api/mcp/routing/adapters/`, `api/mcp/dispatch/handlers/`); a disconnect
  watcher for buffered calls in `api/mcp/tool_call/`; bundle capability aggregation (`domain/bundles/
  bundle_capabilities.py`) takes whether member notifications are delivered as an input; the tools-list handler picks
  the cache scope.
- **CI:** a conformance job in `.github/workflows/ci.yml` against the compose stack, one run per served revision.
- **Docs:** the protocol and troubleshooting pages that describe cancellation and subscriptions; arc42 §11 entry for
  the advertised-but-undelivered capabilities is removed.
- **Related changes:** [add-upstream-session-pooling](../add-upstream-session-pooling/proposal.md) delivers member list
  changes and resource updates; when it lands, the PROT-11 rule here advertises them again without another spec
  change. No ADR: the changes follow ADR-0016 and ADR-0029.
