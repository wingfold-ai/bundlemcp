# 32 — Protocol passthrough (full bidirectional proxy)

**Status:** Accepted · **Origin:** new (metamcp covered only fragments; scope decision: full fidelity)
**Prior art:** `../metamcp/apps/backend/src/lib/config.service.ts` (MCP_TIMEOUT / MCP_RESET_TIMEOUT_ON_PROGRESS / MCP_MAX_TOTAL_TIMEOUT), `../metamcp/apps/backend/src/lib/metamcp/metamcp-proxy.ts` (progressToken forwarding)

## Summary

bundlemcp is a **full-fidelity bidirectional MCP proxy**, not a tools-only
router. Beyond `tools/list`/`tools/call`, it relays progress, cancellation,
logging, ping, list-changed notifications, completions — and **server→client
requests** (sampling, elicitation, roots) from upstreams to the consuming
client — all working across replicas. Motivating case: ultra-mcp's
hyperframes upstream blocks ~130 s per render; without progress-aware
timeouts and cancellation such calls are unusable through a gateway.

## Requirements

### Progress & timeouts

- **PROT-1** When a client's `tools/call` carries `_meta.progressToken`, the
  gateway MUST forward a progress token upstream and relay upstream
  `notifications/progress` back to the client (translating tokens/request ids
  as needed), within the same response stream serving the call.
- **PROT-2** Per-call timeout model, runtime-configurable (`Config`), matching
  metamcp's semantics: `call_timeout` (default 60 s), `reset_timeout_on_progress`
  (default true — each progress notification resets the clock),
  `max_total_timeout` (absolute cap, default 30 min). Timeout produces a
  structured MCP error to the client and a cancellation upstream (PROT-3).
- **PROT-3 Cancellation:** a client `notifications/cancelled` MUST reach the
  upstream call it targets even when it arrives at a different replica than
  the one holding the in-flight upstream request — routed via Redis pub/sub
  keyed by session + request id ([SES cross-replica signaling —
  30-session-management.md](30-session-management.md)). Cancellation also
  triggers the metering post-call hook with `status=error`
  ([MID-3](31-middleware.md)).

### Server→client requests (sampling, elicitation, roots)

- **PROT-4** Upstream-initiated requests — `sampling/createMessage`,
  `elicitation/create`, `roots/list` — MUST be relayed to the downstream
  client and the client's response routed back to the requesting upstream,
  including across replicas (the client's event stream may be pinned to a
  different replica than the upstream connection; delivery goes through the
  same pub/sub routing as PROT-3).
- **PROT-5** Capability-gated: an upstream request type is relayed only if the
  downstream client advertised the corresponding capability at `initialize`;
  otherwise the gateway answers the upstream with a method-not-supported
  error itself. The capability set offered TO each upstream MUST therefore be
  the intersection of what the client offered and what the gateway can relay.
- **PROT-6** Relayed server→client requests inherit the pending `tools/call`'s
  timeout budget (PROT-2); an unanswered elicitation/sampling request times
  out with the call.

### Notifications & misc

- **PROT-7** `notifications/message` (logging) from upstreams are relayed to
  the client when it enabled logging; `logging/setLevel` from the client is
  fanned out to member upstreams that support it.
- **PROT-8** `ping` is answered by the gateway in both directions; a client
  ping counts as session activity and refreshes the SES-1 TTL.
- **PROT-9** `completion/complete` (prompt/resource-template argument
  completion) is routed to the owning upstream using the same prefix rules as
  tools ([BND-3](12-bundles.md)).
- **PROT-10** Upstream `notifications/*/list_changed` (tools, prompts,
  resources) trigger re-discovery ([DISC-1](11-tool-discovery.md)) and are
  propagated to connected clients per [BND-7](12-bundles.md).

### Capability & version aggregation

- **PROT-11** The bundle's `initialize` result advertises a capability iff at
  least one enabled member server supports it. The set is computed from the
  per-server `capabilities` snapshot captured at discovery
  ([DISC](11-tool-discovery.md)): `tools` (always — the gateway supports tools
  even with zero members), `prompts`, `resources`, `completions`, and
  `logging`. `listChanged: true` is advertised where the gateway can emit it
  (tools always; prompts/resources when ≥1 member advertises it);
  `resources.subscribe: true` when ≥1 member supports it.
- **PROT-12** Protocol version: the gateway declares a supported-version window
  and negotiates the highest version common with each side independently — with
  the client at its `initialize`, and with each upstream on connect. Message
  shapes are translated across the bounded set of differences within the
  window; a client requesting a version outside the window fails `initialize`
  with a clear error rather than degrading silently.

## Implementation

**Implemented** ([ADR-0021](../docs/adr/0021-mcp-surface-completion.md)):
prompts/resources/completions routing (PROT-9), capability aggregation
(PROT-11), version negotiation + bounded translation (PROT-12), and the
roots/logging relay (PROT-4/PROT-7) on the request/response path and within an
active call. **Pooling-dependent residual:** any upstream→client *push* that
must arrive between calls — `notifications/resources/updated` for a
`resources/subscribe`, PROT-7 upstream `notifications/message`, and PROT-10
upstream `*/list_changed` **outside an active call** — requires a persistent
upstream connection, which the per-call-connection model (ADR-0012) does not
provide. These capabilities are advertised and delivered *within* an active
call window; full between-call push lands with connection pooling
([SES-8](30-session-management.md), ADR-0012).

## Out of scope

- Persisting/replaying server→client requests across a *client* disconnect —
  if the client's stream is gone, pending upstream requests fail fast.
- Rate-limiting relayed notifications (revisit if an upstream floods).

## Open questions

- ~~How much of PROT-4's relay FastMCP v3 provides natively? What is the
  cross-replica correlation design?~~ **Resolved**
  ([ADR-0016](../docs/adr/0016-relay-design.md)): the downstream half is built
  on bundlemcp's own endpoint edge (SSE call responses + GET event stream);
  the upstream half uses FastMCP's client `progress_handler` /
  `elicitation_handler` / `sampling_handler`. Cross-replica routing is a
  publish-only Redis `bmcp:signal:*` bus feeding per-replica registries of
  streams/calls/reply-futures (`gateway/signals.py`, `gateway/streams.py`).
  One residual limit is documented in ADR-0016: upstream `list_changed`
  outside an active call awaits connection pooling (ADR-0012).
