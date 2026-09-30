# ADR-0039: Upstreams are inspected, and their refusals classified, below the MCP client

**Status:** accepted · **Date:** 2026-09-24 · **Extends:** [ADR-0030](0030-fastmcp-4.md)

## Context

Registering a server asked the operator for `auth_mode`, `identity_mode`,
`forward_headers`, `send_identity_header` and `protocol_mode` before the
gateway had ever contacted it. Operators reported not knowing which options
applied. Reading the code showed that part of the confusion was structural:

- `none` and `static_headers` behaved identically — static headers were sent
  whenever stored — so the choice between them meant nothing
  (`deploy/seed.yaml` registers `seo-gsc` with an `authorization` static
  header and the default `auth_mode: none`).
- `identity_mode` only has an effect with upstream OAuth, yet was asked for
  every server.
- Whether a server needs OAuth is published by the server itself: since MCP
  2025-06-18 an OAuth-protected server challenges with
  `WWW-Authenticate: Bearer resource_metadata=…` or serves an RFC 9728
  document at a well-known location; the client is required to support both.

The gateway could not act on that evidence. The MCP SDK (mcp 2.1.1) reports
every non-2xx HTTP answer — 401, 403, 404, 405, a web page — as the same
generic `INTERNAL_ERROR`, so discovery's `last_error` read "Server returned
an error response" whatever happened, and the upstream-OAuth retry fired on
any failure, not on a 401.

State-of-the-art clients converge on one pattern: ask for the URL, probe it,
pre-fill what was detected, and ask only the rest (claude.ai custom
connectors mark detected settings as such; Cloudflare MCP portals connect on
save; Smithery reports connections as states such as `auth_required` and
`input_required`). VS Code's issue #334970 records the failure mode to avoid:
starting OAuth on any 401 turns an expired API key into a confusing OAuth
prompt.

## Decision drivers

- The operator should answer only what the upstream cannot: which key, whose
  account, whether to send caller identity.
- Classification must come from HTTP evidence, not from error strings.
- A 401 alone is never evidence of OAuth.
- No new state a request depends on outside Postgres and Valkey (spec 30).

## Decision

- **Observe below the MCP client.** The upstream client factory takes an
  `observer`, a `ResponseLog` the caller creates. The fastmcp transport gets
  an `httpx2.Auth` hook (`ResponseObserver`) that records every response the
  client cannot use — status, media type, parsed `WWW-Authenticate` — without
  reading the body, so event streams stay streams. Protocol negotiation stays
  with the SDK's `negotiate_auto`.
- **Connection state.** A probe that gets no MCP answer raises
  `ProbeFailure` classified by a pure domain rule into `oauth_required`,
  `credential_required`, `insufficient_scope`, `not_mcp`, `unreachable`,
  `egress_denied` or `error`. A refusal without an OAuth challenge is only
  upgraded to `oauth_required` after following the OAuth discovery chain
  (`ConnectionDiagnoser`), and never for a server that already sends a
  credential. Discovery stores the state on every probe
  (`mcp_servers.connection_state`, migration 0006), with `account_required`
  for an OAuth server nobody has connected. A state that contradicts the
  configuration is exposed as `configuration_mismatch`.
- **Inspection.** `POST /servers:inspect` runs the same probe against a URL
  without storing anything, retries once with `/mcp` appended when the URL
  is not an MCP endpoint, follows the OAuth chain for a refusal, and returns
  a suggested `ServerUpsert`. Candidate credential headers are used for that
  probe only. `POST /servers:from-server-json` drafts a registration from a
  registry `server.json` (its declared headers are the only standard
  description of API-key credentials).
- **Settled and derived fields.** `none`/`static_headers` is settled from the
  stored headers on every write. `send_identity_header` defaults to on only
  for hosts on the gateway's own network. Fields a write omits
  (`send_identity_header`, `protocol_mode`) keep their stored value on
  update.
- **One question in the UI.** Registration asks "where does the credential
  come from?" with the detected answer pre-selected; the remaining fields
  move under *Advanced*.
- **Targeted retries.** A tool call refreshes and retries only on an
  observed 401 from an upstream-OAuth server; a 401 from a static credential
  is reported as a refused credential.

## Alternatives considered

- **Parse the MCP client's error text.** It carries no status for most
  failures; the SDK deliberately collapses them.
- **A hand-written HTTP probe instead of the SDK.** Would duplicate protocol
  negotiation (`server/discover` versus `initialize`, -32022 handling) that
  the SDK already implements correctly; observing the SDK's own transport
  keeps one negotiation path.
- **An `auth_mode: auto` resolved at write time.** Hides the decision inside
  a PUT and still cannot choose an API key or whose account to use; a
  separate inspection step shows the evidence and leaves the choice explicit.
- **Treat any 401 as OAuth.** The VS Code failure mode.

## Consequences

### Positive

- Registration asks one question instead of five, with the answer usually
  already selected; OAuth client fields appear only when the provider
  offers no automatic registration.
- Operators see why a server fails (`credential_required`, `not_mcp`, …)
  and the fix for a misconfiguration.
- Discovery, inspection and tool calls share one classification.

### Trade-offs

- Every upstream client carries a small auth hook; the per-response cost is
  a header parse on unusable responses only.
- Classifying a keyless refusal may cost one extra round of OAuth discovery
  requests (well-known documents) per failed probe.
- `send_identity_header` now defaults off for public hosts; a registrar that
  relied on the old default for an external server must send it explicitly.
