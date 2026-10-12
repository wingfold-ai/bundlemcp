# ADR-0045: The published surface says "upstreams", with deprecated aliases for "servers"

**Status:** accepted · **Date:** 2026-10-12

## Context

The resource the gateway proxies to is called a *server* in the management API (`/api/v1/servers`), the bootstrap
and export documents (`servers:`), the OpenAPI tag, and the admin UI (**Servers**). To a reader new to MCP the word is
ambiguous: the gateway is itself an MCP server to its clients, and an HTTP server to everyone. The documentation already
says "upstream server" when it needs to be unambiguous, so the product uses two names for one thing.

The names are published. A private application layer's registrar drives `PUT /api/v1/servers/{name}` on every deploy,
operators keep bootstrap files in their own repositories, and links to `/servers` pages sit in runbooks. A rename
without a transition breaks all three on upgrade.

Inventory at `9ec1a70`:

| Surface | Occurrences |
|---|---|
| Management API routes under `/servers` | 13, plus 3 bundle-membership routes under `/bundles/{name}/servers` |
| OpenAPI tag `servers` | 1 controller |
| Bootstrap document keys | `servers` at the top level and in each bundle entry |
| Export / import document | `servers` key specified (EXP-1); not implemented yet |
| Admin UI | 2 pages under `/servers`, 1 nav entry, 9 files referencing the label or route |
| User documentation | 19 references to `/api/v1/servers` across 5 pages, plus `deploy/seed.yaml` |
| Payload fields | `server_name`, `server_id`, `server_url`, `server_info`, the metering context's `server`, the audit record's `server_name` |
| Environment variables | none |

## Decision drivers

- One name for one thing, chosen for what the thing is relative to the gateway, not for its history
  (design-principles §1).
- No deployment breaks on upgrade; automation gets a stated window and a visible signal to move.
- Generated clients and new documentation learn only the new names.
- Contracts that are versioned on their own (the metering hook) are not changed as a side effect.

## Decision

- **Name.** *Upstream server*, *upstream* for short: the position of the resource relative to the gateway, which is
  the property that tells it apart from the gateway itself. On the wire it is always the short form: `upstreams` in
  paths, the OpenAPI tag and JSON and YAML keys, `/upstreams` for UI routes. Prose and UI titles say *upstream
  server*; the documentation introduces the term as "upstream server (upstream for short)" and uses either afterwards,
  so the wire name is one a reader has already met ([SRV-16](../../spec/10-server-registry.md),
  [UI-7](../../spec/60-admin-ui.md)).
- **Scope.** Collection nouns only: route paths, document keys, the tag, UI copy and routes. Payload field names stay
  (`server_name` on a tool or an audit record is already qualified by its object), and so do Python class names; both
  can follow later without touching the published contract.
- **Transition.** Old routes stay as aliases with identical behaviour and `Deprecation`, `Sunset` and
  `Link: rel="successor-version"` headers, a rate-limited `WARN` per caller, and a metric
  ([API-8](../../spec/40-management-api.md)). They are left out of the OpenAPI document. The old bootstrap key is
  accepted with a `WARN`; a document carrying both keys is rejected ([BOOT-8](../../spec/41-bootstrap.md)). Old UI
  routes redirect. The window is at least 180 days from the first release that ships the new names, then `410 Gone`
  for one minor release, then `404`.

## Alternatives considered

- **`/api/v1/upstream-servers` and `upstream_servers:`.** The full term on the wire. Rejected as long in every path and
  key a registrar or bootstrap file writes, when "upstream" used as a noun is already common in gateway and proxy
  vocabulary; introducing the short form in the documentation alongside the full term keeps the two from reading as
  different things.
- **Rename the fields too** (`upstream_name`, metering `upstream`). Consistent, but changes the metering
  hook contract that ADR-0042 just versioned, and the audit API that consumers query, for no gain in clarity.
- **Documentation-only rename.** Cheapest, but leaves the API and UI saying "Servers", so a reader moving from the
  docs to the product meets two names for one thing again.
- **Bump to `/api/v2`.** A whole version for one collection rename; every unchanged route would move with it.

## Consequences

**Positive:**

- A reader new to MCP never has to guess which "server" a page or a route means.
- Automation keeps working through the window and is told, per request, exactly what to change.

**Trade-offs:**

- Two route trees serve the same resource for the length of the window, and the alias layer and its tests have to be
  kept until the sunset date.
- Payload fields keep the short `server_*` names, so the rename is visible in paths and keys but not inside bodies.
