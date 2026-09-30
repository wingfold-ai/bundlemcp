# 10 — Server registry

**Status:** Accepted · **Origin:** metamcp carry-over (narrowed to Streamable HTTP)
**Prior art:** `../metamcp/apps/backend/src/db/schema.ts` (`mcp_servers`), `../metamcp/packages/zod-types/src/mcp-servers.zod.ts`

## Summary

CRUD for upstream MCP servers. bundlemcp connects to upstreams **exclusively
over Streamable HTTP** — no stdio process spawning, no SSE. This removes
metamcp's largest complexity source (process pools, crash tracking, env
resolution, Node+Python runtime images).

## Requirements

- **SRV-1** A server has: unique slug-safe `name` (doubles as the tool prefix),
  optional `description`, `url` (http/https), `static_headers`,
  `forward_headers`, `auth_mode` (`none` | `static_headers` |
  `upstream_oauth` | `delegated_token`), a `connection_state` (SRV-12), and a
  `capabilities` snapshot captured at discovery
  ([DISC-6](11-tool-discovery.md)) that feeds capability aggregation
  ([PROT-11](32-protocol-passthrough.md)). See
  [02-domain-model.md](02-domain-model.md). `none` and `static_headers`
  differ only in whether static headers are stored, so the gateway derives
  one from the other on every write: a server that is neither
  `upstream_oauth` nor `delegated_token` is `static_headers` exactly when it
  holds at least one static header.
- **SRV-2** Create/update/delete/list/get MUST be available in the management
  API ([40-management-api.md](40-management-api.md)) and the UI. Create and
  update MUST validate the config by connecting to the upstream (protocol
  negotiation per SRV-10) and running `tools/list`, storing discovered tools on
  success
  ([11-tool-discovery.md](11-tool-discovery.md)). A failed probe stores the
  server with `health_status=error` (explicitly allowed: registering a server
  that isn't up yet), never blocks creation from the API.
- **SRV-3** `static_headers` values are secrets: write-only in the API
  (responses return key names only), never logged ([DOM-3](02-domain-model.md)).
- **SRV-4** `health_status` + `last_error` MUST be maintained: set to `error`
  with a message after `N` consecutive connection failures (default 3,
  runtime-configurable), reset to `ok` on the next successful connect —
  metamcp's error tracker semantics, minus the process babysitting.
- **SRV-5** Renaming a server MUST be rejected while it is a member of any
  bundle (the name is baked into prefixed tool names), unless the rename
  request carries an explicit `force` flag that acknowledges client-visible
  tool names will change.
- **SRV-6** Config changes (url/headers/auth) MUST invalidate any pooled
  upstream connections for that server via the config-invalidation event
  stream ([33-state-propagation.md](33-state-propagation.md),
  [30-session-management.md](30-session-management.md)).
- **SRV-8** All gateway-initiated requests to server URLs (probes, discovery,
  live calls) pass the egress policy ([SEC-1/SEC-2](70-security.md)).
- **SRV-9** Optional background health polling: a global flag +
  interval (`Config`) pings registered servers so `health_status` stays fresh
  even for servers not currently receiving traffic; off by default
  (opportunistic updates per SRV-4 remain the baseline).
- **SRV-10** Protocol era per upstream ([PROT-21](32-protocol-passthrough.md)):
  a server has a `protocol_mode` — `auto` (default: probe `server/discover`,
  fall back to `initialize`), `legacy` (always the `initialize` handshake, for
  upstreams whose tools need server-initiated requests), or a pinned modern
  revision (`YYYY-MM-DD`). Discovery records the negotiated revision as
  `protocol_version`, shown in the API and UI so an operator can see which
  upstreams still speak the handshake era. An update that omits
  `protocol_mode` keeps the stored value rather than resetting it to `auto`.

## Guided registration

What a server needs is mostly a fact about the upstream, which the gateway
can ask it; only the choices the upstream cannot answer are put to the
operator ([ADR-0039](../docs/adr/0039-server-inspection-and-connection-state.md)).

- **SRV-11 Inspection.** `POST /servers:inspect` takes a `url` and optional
  candidate `headers`, stores nothing, and reports what the upstream is:
  its `connection_state` (SRV-12), negotiated `protocol_version`,
  `serverInfo` (name, title, description, website), tool count, and — for an
  OAuth-protected upstream — the authorization server, the scopes the
  resource asks for, and how the gateway can identify itself there
  (`preregistered_required`, `metadata_document`, `dynamic_registration`;
  [UPO-1](23-upstream-oauth.md)). It returns a suggested `ServerUpsert`
  (slug-safe name from `serverInfo`, description, `auth_mode`,
  `identity_mode`, `send_identity_header`) that a caller can submit as is.
  Every request passes the egress policy ([SRV-8](#requirements)); candidate
  header values are used for the probe only and never stored, logged or
  echoed.
- **SRV-12 Connection state.** Discovery and inspection classify their
  outcome from the upstream's HTTP response, not from the MCP client's
  error text:

  | State | Signal |
  |---|---|
  | `ready` | a valid `server/discover` or `initialize` result |
  | `oauth_required` | 401/403 with a `Bearer` challenge naming `resource_metadata`, or a protected resource document at a well-known location |
  | `account_required` | the server is `upstream_oauth` and no account is connected to probe with ([UPO-9](23-upstream-oauth.md)) |
  | `insufficient_scope` | 403 with `error="insufficient_scope"` ([UPO-10](23-upstream-oauth.md)) |
  | `credential_required` | 401/403 with no OAuth metadata anywhere |
  | `not_mcp` | 404/405/406/415 without a JSON-RPC error body, or a non-MCP body |
  | `unreachable` | connection, TLS or timeout failure |
  | `egress_denied` | the egress policy refused the URL ([SEC-1](70-security.md)) |
  | `error` | anything else |

  The state is stored on the server (`unknown` until the first probe) and
  shown in the API and UI. A stored state that contradicts the configured
  `auth_mode` — `oauth_required` on a server without upstream OAuth,
  `credential_required` on one without static headers — is reported as a
  mismatch the UI offers to fix. OAuth is never started for a server because
  of a 401 alone: only an OAuth challenge or document is evidence of OAuth.
- **SRV-13 Identity header default.** `send_identity_header` is optional on
  write. Omitted when a server is created, it is derived; omitted on an
  update, the stored value is kept. The derived value is on for a server on
  the gateway's own network (a host name without a dot, `localhost`, a name
  under `.local`, `.internal`, `.localhost` or `.svc`, or a private,
  loopback or link-local address) and off for every other host, so a third-party server
  never receives caller identifiers unless an operator opts in.
- **SRV-14 Header rules at write time.** A `forward_headers` entry whose
  client or upstream name is on the [FWD-2](24-identity-forwarding.md)
  deny-list is rejected with 422 when the server is written, not only
  skipped at call time.
- **SRV-15 Registry `server.json` import.** `POST /servers:from-server-json`
  accepts an MCP Registry `server.json` document and returns a draft: the
  first `streamable-http` remote's URL (URL template variables listed for
  the operator to fill), a slug-safe name and description, and the remote's
  declared `headers` with their `description`, `isRequired` and `isSecret`
  flags, so the UI can render the credential form the server's publisher
  described. It stores nothing and fetches nothing; `sse` remotes are
  reported as unsupported. This imports one document an operator already
  has — it is not a registry browser (decision log: marketplace).

## The stdio pattern (documentation, not code)

- **SRV-7** The README/docs MUST document how to run a stdio-only MCP server
  behind bundlemcp: wrap it in a sidecar container exposing Streamable HTTP
  (e.g. `mcp-proxy`, Supergateway, or FastMCP's own proxy runner) and register
  the sidecar's URL. A compose snippet example is part of the docs deliverable.

## Out of scope

- STDIO and SSE upstream transports (decision log).
- Auto-discovery of servers (the application layer's registrar does that, via the
  management API).

## Open questions

- Per-server request timeout overrides vs. global-only (lean: global `Config`
  values first, per-server later if needed).
