# ADR-0030: FastMCP 4 / MCP SDK v2 as the upstream client, negotiated per server

**Status:** accepted · **Date:** 2026-09-05 · **Amends:** [ADR-0002](0002-fastmcp-v3.md), [ADR-0012](0012-per-call-upstream-connections.md)

## Context

FastMCP 3.4 on MCP SDK 1.28 speaks 2025-11-25 at the newest: it opens every
upstream with `initialize` and cannot reach a server that only implements
2026-07-28. FastMCP 4.0 (31 August 2026, on SDK 2.0) is a dual-era client:
`mode="auto"` probes `server/discover` and falls back to the handshake,
`mode="legacy"` forces the handshake, and a pinned version adopts it. Its
`elicitation_handler`, `sampling_handler` and `roots` callbacks serve both a
handshake upstream's server-initiated requests and a modern upstream's
`input_required` results, driven by the same loop.

A spike against 4.0.3 (in-process servers, both eras) established:

- `client.server_capabilities`, `client.protocol_version`,
  `client.instructions` are populated in both eras; `initialize_result` is
  `None` on a modern connection.
- `client.session.call_tool(..., allow_input_required=True)` returns the raw
  `InputRequiredResult`, and the retry accepts `input_responses` and
  `request_state` — the basis for stateless pass-through (ADR-0029). The same
  holds for `read_resource` and `get_prompt`.
- A FastMCP 4 *server* answers `server/discover`, so `mode="auto"` against it
  negotiates the modern era; its tools that still call the imperative
  `ctx.elicit` then fail with "elicitation via server-initiated requests is
  unavailable on 2026-07-28 connections". Such an upstream must be pinned to
  `legacy`.
- SDK v2 renames every model field to snake_case (`inputSchema` →
  `input_schema`, `isError` → `is_error`); JSON aliases are unchanged.

## Decision

- Depend on `fastmcp>=4.0.3` (SDK 2.1). The client factory
  (`gateway/upstream.py`) passes the server's `protocol_mode` as `mode`;
  discovery reads `server_capabilities` and records `protocol_version` on
  `McpServer` (SRV-10).
- `McpServer.protocol_mode` (`auto` default, `legacy`, or a pinned revision)
  is the operator's remedy for an upstream that advertises the modern era but
  whose tools need the handshake's back-channel.
- Modern-era upstream calls go through `client.session` with
  `allow_input_required=True`, so the gateway sees `input_required` itself;
  handshake-era calls keep using the FastMCP callbacks.
- Test fixtures cover both upstream eras with the same in-process FastMCP 4
  server: `Client(server, mode="legacy")` for a handshake upstream (tools use
  `ctx.elicit`), `mode="auto"` for a modern one (tools return
  `InputRequiredResult` and read `ctx.input_responses`).

## Reasons

- Latest-stable policy (ARC-1), and the only way to consume modern-only
  upstreams.
- One handler shape for both upstream eras is what makes the relay (ADR-0016)
  and the park-and-resume bridge (ADR-0029) era-agnostic on the upstream side.
- The per-call connection model (ADR-0012) is untouched: negotiation happens
  on each connect, which is exactly where `mode` applies.

## Consequences

- (+) Modern upstreams work; handshake upstreams keep working; the newest
  common revision is used per server automatically.
- (+) Cache hints and `resultType` from modern upstreams arrive typed.
- (−) snake_case renames touch discovery, the relay and every test that reads
  SDK models; `httpx2` replaces `httpx` inside the SDK.
- (−) Operators must pin `legacy` for FastMCP 4 upstreams that still use
  imperative elicitation; the recorded `protocol_version` makes those
  visible.
