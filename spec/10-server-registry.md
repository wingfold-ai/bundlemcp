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
  `upstream_oauth`), and a `capabilities` snapshot captured at discovery
  ([DISC-6](11-tool-discovery.md)) that feeds capability aggregation
  ([PROT-11](32-protocol-passthrough.md)). See
  [02-domain-model.md](02-domain-model.md).
- **SRV-2** Create/update/delete/list/get MUST be available in the management
  API ([40-management-api.md](40-management-api.md)) and the UI. Create and
  update MUST validate the config by attempting an MCP `initialize` +
  `tools/list` against the upstream, storing discovered tools on success
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

## The stdio pattern (documentation, not code)

- **SRV-7** The README/docs MUST document how to run a stdio-only MCP server
  behind bundlemcp: wrap it in a sidecar container exposing Streamable HTTP
  (e.g. `mcp-proxy`, Supergateway, or FastMCP's own proxy runner) and register
  the sidecar's URL. A compose snippet example is part of the docs deliverable.

## Out of scope

- STDIO and SSE upstream transports (decision log).
- Auto-discovery of servers (application-layer's registrar does that, via the
  management API).

## Open questions

- Per-server request timeout overrides vs. global-only (lean: global `Config`
  values first, per-server later if needed).
