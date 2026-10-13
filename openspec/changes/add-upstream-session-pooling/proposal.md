# Proposal: add upstream session pooling

## Why

Every upstream request opens a fresh FastMCP client (`infrastructure/fastmcp/client_factory.py`): connect, `initialize`,
call, close ([ADR-0012](../../../docs/adr/0012-per-call-upstream-connections.md)). That keeps identity isolation
trivially right, but it costs an upstream handshake per call, gives stateful upstreams a new session on every call, and
leaves the gateway with no standing upstream channel. Everything an upstream pushes **between** calls is therefore lost:
`notifications/*/list_changed`, log messages and `notifications/resources/updated`. The gateway advertises
`resources.subscribe` and accepts `resources/subscribe` without ever pushing an update, and the session record's
`UpstreamBinding.upstream_session_id` is never written — its `identity_key` is the bare `sub` and is never read
(arc42 §11, ADR-0021 "per-call-connection boundary").

The original session spec (SES-5 to SES-9), SES-21, PROT-10, the PROT-7 fan-out and the pooling half of UPS-6 and
AUTH-31 were written for a pooled model that was deferred. This change builds it.

## What Changes

- Upstream sessions become **data in Valkey** (upstream session id, server URL, a fingerprint of the headers — never the
  header values), re-attachable from any replica; live HTTP connections stay per-replica transport (SES-5).
- A handshake-era session's binding carries a **real upstream session**; identity-free servers may share pooled upstream
  sessions between callers, identity-bound ones never (SES-6), keyed by an identity key that hashes the forwarded header
  values, not just `sub` (AUTH-31).
- Upstream 404 ("session not found") or transport loss → re-initialize, rebind, retry **once**; repeated failure → a
  structured error that also counts toward the server's health (SES-7).
- Per-replica connection caps, global and per server, runtime-configurable, with LRU eviction of identity-free sessions
  first and a per-call connection as the fallback; no pre-warming (SES-8).
- A `server` invalidation event tears down that server's pooled transports on every replica (SES-9, SES-21, UPS-6).
- Upstream `list_changed` notifications trigger re-discovery and reach clients' GET and `subscriptions/listen` streams
  (PROT-10); `logging/setLevel` is fanned out to members that support logging and upstream log messages are pushed
  between calls (PROT-7); `subscriptions/listen` delivers member prompt/resource list changes and resource updates
  (PROT-17); handshake `resources/subscribe` is relayed and its updates pushed (PROT-23, new).
- The in-process-only rule holds: the pool is a per-replica cache of transports; everything a request depends on (which
  upstream session a binding names, which resources are subscribed) is in Valkey.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `sessions`: ADDED SES-5 (upstream sessions as data), SES-8 (connection caps), SES-9 (pool invalidation);
  MODIFIED SES-6 (bindings carry a real upstream session) and SES-7 (re-initialize, rebind, retry once).
- `sessions`: ADDED SES-21 (server invalidation tears down pooled transports).
- `protocol`: ADDED PROT-10 (upstream `list_changed` → re-discovery + propagation) and PROT-23 (resource
  subscriptions relayed); MODIFIED PROT-7 (setLevel fan-out, between-call log push) and PROT-17 (member list changes
  and `resourceSubscriptions` delivered).
- `upstreams`: MODIFIED UPS-6 (config changes invalidate pooled connections).
- `auth`: MODIFIED AUTH-31 (binding key hashes the forwarded header values).

## Open decision

- **Retry scope on transport loss (SES-7).** The original SES-7 retries the in-flight request once on "transport loss".
  For `tools/call` a connection lost *after* the request was sent may already have run the tool, so a blind retry can
  repeat side effects. The delta retries a `tools/call` only when the upstream provably did not run it (404 for the
  session, or the connection failed before the request was sent) and retries read-only methods on any transport loss.
  Maintainers confirm this narrowing, or keep the original wording and accept duplicate side effects.
- **Where the caps apply (SES-8).** The delta applies the global and per-server caps **per replica** (transports are
  per replica). A cluster-wide cap would need a shared counter in Valkey on every checkout. Confirm per-replica.

## Impact

- **Code:** a pool contract in `application/contracts/upstream/` and a resource-subscription contract in
  `application/contracts/live_state/`; an upstream-notification router in `application/serving/`; adapters in
  `infrastructure/fastmcp/` (the pool, built on the existing client-factory seam) and `infrastructure/valkey/` (the
  subscription index, the re-discovery gate); the pool key, identity-freedom and the retry policy as domain rules;
  `UpstreamCall`, `MemberFanout` and the setLevel, subscribe and listen handlers lease from the pool; wiring in `main/`.
  Design: [design.md](design.md).
- **Config:** new runtime keys `upstream_sessions_max`, `upstream_sessions_per_server_max`,
  `upstream_session_idle_timeout`.
- **Session record:** `UpstreamBinding` gains optional fields with defaults, so the record schema version does not
  change and replicas of the previous build keep reading records during a rolling deploy (DEP-6).
- **Settings:** `BUNDLEMCP_UPSTREAM_POOLING_ENABLED` (default on); off restores per-call connections as a rollback path.
- **ADR:** a new ADR (next free number in `docs/adr/`) supersedes ADR-0012 and amends ADR-0021's per-call boundary.
- **Docs:** arc42 §5/§6/§8/§11, `docs/adr/README.md`, `packages/bundlemcp/bundlemcp/api/mcp/README.md`, the
  operations and configuration pages for the new keys.
- **Related changes:** [complete-session-lifecycle](../complete-session-lifecycle/proposal.md)'s upstream-restart
  recovery test (SES-12) and its sweeper's binding release depend on this change.
  [complete-protocol-passthrough](../complete-protocol-passthrough/proposal.md) gates `resources.subscribe` and member
  `listChanged` on delivery (PROT-11); once this change lands those flags are advertised again.
  [complete-upstream-health](../complete-upstream-health/proposal.md) provides the shared failure counter SES-7 feeds.
