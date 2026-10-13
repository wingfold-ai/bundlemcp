# ADR-0021: Complete the MCP surface — prompts/resources/completions passthrough, capability aggregation, version negotiation, roots/logging relay

**Status:** accepted · **Date:** 2026-07-05 · **Amended by:** [ADR-0029](0029-dialects-and-dual-era-edge.md),
[ADR-0043](0043-contact-upstreams-only-with-a-reason.md), [ADR-0044](0044-bundle-owned-prompts-and-resources.md)

## Context

The bundled endpoint was a faithful *tools-plane* MCP server but returned `-32601` for `prompts/*`, `resources/*`, and
`completion/complete`, advertised a hardcoded tools-only capability set, echoed the client's protocol version without
negotiating, and relayed only sampling/elicitation (not roots or logging). Spec 32/12 declare all of this in-scope (a
"full-fidelity bidirectional proxy", ADR-0008), so the specs overstated what was built. This ADR records the design that
closes the gap, and resolves five points the specs left under-specified.

## Decision drivers

- Following BND-8 and tool discovery (live passthrough, no cache/curation) makes the feature far smaller than mirroring
  the Tool/BundleTool machinery, and matches the spec's intent.
- A cached capability snapshot keeps `initialize` fast and correct even when a member is down (UPS-20), unlike a live
  per-initialize probe.
- Stateless fan-out for resource reads avoids non-standard URIs and cross-replica cache coherency for a rare
  (same-URI-across-members) case.

## Decision

- **Prompts/resources/completions are live, uncurated passthrough.** No `Prompt`/`Resource` content tables and no
  per-bundle curation (BND-8; tool discovery says not cached in v1). Each request fans out concurrently to the enabled
  member servers, isolating a down member (skip + WARN, never a silent partial — UPS-20). Tools remain the only
  cached/curated surface.
- **Prompt names are always prefixed** `server__prompt` (BND-2 first-`__` scheme); `prompts/get` and completion
  prompt-refs de-prefix to the owner.
- **Resource URIs pass through unchanged.** `resources/list` / `resources/templates/list` merge members verbatim,
  de-duplicating by URI (first enabled member wins, collisions logged). `resources/read`, `resources/subscribe`, and
  resource-template completions resolve the owner by **stateless fan-out** — try enabled members in order, first owner
  wins. Chosen over URI-rewriting (breaks client URI validation) and a URI→owner cache (extra Redis state on the read
  path) for a stateless, cross-replica-safe v1.
- **Capability aggregation (PROT-11) reads a per-server snapshot.** Discovery captures each upstream's advertised
  `initialize` capabilities into a new `McpServer.capabilities` JSON column (UPS-22); `initialize` aggregates over
  enabled members (advertise a capability iff ≥1 supports it; `tools` always; `listChanged`/`resources.subscribe` where
  the gateway can honor it) without fanning out to members on the hot path.
- **Version negotiation (PROT-12)** declares a supported-version window, negotiates the highest common version with the
  client (fail `initialize` with a clear error if none) and independently with each upstream, and translates the bounded
  set of shape differences within the window (`gateway/protocol_version.py`).
- **Read-only passthrough** (`prompts/get`, `resources/read`, `completion/complete`) reuses upstream-OAuth bearer
  resolution + header forwarding but does **no metering and writes no tool-call audit** — audit is tool calls only.
- **Roots (PROT-4)** joins sampling/elicitation in the relay handler set, capability-gated on the client's `roots`
  (PROT-5 intersection). **Logging (PROT-7)**: upstream `notifications/message` relay to the client and
  `logging/setLevel` fan-out to members that support logging.

## The per-call-connection boundary (honest scope)

The gateway uses per-call upstream connections (ADR-0012), so there is no standing upstream channel between calls. Every
request/response capability above, and relay *within* an active call, is implemented. But upstream→client
**push that must arrive between calls** — `notifications/resources/updated` for a `resources/subscribe`, PROT-7 upstream
log push, and PROT-10 upstream `*/list_changed` outside an active call — needs a persistent connection. These are
advertised and delivered within an active-call window; full between-call push lands with connection pooling (SES-8,
ADR-0012). This is recorded in spec 32's Implementation note and arc42 §11, not hidden behind a green capability flag.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- The endpoint is a full MCP server for the request/response plane: prompts, resources, completions, aggregated
  capabilities, version negotiation, and roots/logging relay — each test-covered.
- No new content/curation tables; the only schema change is one JSON column.

### Trade-offs

- A `resources/read` for an unknown URI fans out to all enabled members before failing; same-URI collisions are
  first-wins.
- Subscribe/log/list-changed **push between calls** remains pooling-dependent (ADR-0012). Advertised capabilities are
  honest only within an active call.
- Version translation covers only the declared window; upstreams outside it fail fast rather than silently degrading (by
  design, PROT-12).

