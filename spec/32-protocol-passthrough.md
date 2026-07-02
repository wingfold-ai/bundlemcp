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
  least one enabled member server supports it (tools/prompts/resources
  computed from live+cached knowledge; `listChanged: true` where the gateway
  can emit it). The gateway itself always supports tools.
- **PROT-12** Protocol version: the gateway negotiates its supported version
  with each side independently and translates where message shapes differ
  between the client's and an upstream's negotiated versions; unsupported
  version combinations fail `initialize` with a clear error rather than
  degrading silently.

## Out of scope

- Persisting/replaying server→client requests across a *client* disconnect —
  if the client's stream is gone, pending upstream requests fail fast.
- Rate-limiting relayed notifications (revisit if an upstream floods).

## Open questions

- How much of PROT-4's relay FastMCP v3 provides natively vs. requiring
  low-level SDK plumbing — answered by the same implementation spike as
  [30-session-management.md](30-session-management.md)'s open question.
