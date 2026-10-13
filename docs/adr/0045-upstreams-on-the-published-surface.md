# ADR-0045: The published surface says "upstreams"

**Status:** accepted · **Date:** 2026-10-12

## Context

The resource the gateway proxies to is called a *server* in the management API (`/api/v1/servers`), the bootstrap
and export documents (`servers:`), the OpenAPI tag, and the admin UI (**Servers**). To a reader new to MCP the word is
ambiguous: the gateway is itself an MCP server to its clients, and an HTTP server to everyone. The documentation already
says "upstream server" when it needs to be unambiguous, so the product uses two names for one thing.

The names are published, but nobody depends on them yet: the gateway is not in active use, and the application layer
whose registrar will drive the management API has not been connected. A rename now costs one coordinated change; the
same rename after adoption would need a deprecation window and an alias layer to get through it.

Inventory at `9ec1a70`:

| Surface | Occurrences |
|---|---|
| Management API routes under `/servers` | 13, plus 3 bundle-membership routes under `/bundles/{name}/servers` |
| OpenAPI tag `servers` | 1 controller |
| Bootstrap document keys | `servers` at the top level and in each bundle entry |
| Export / import document | `servers` key specified (MGMT-17); not implemented yet |
| Admin UI | 2 pages under `/servers`, 1 nav entry, 9 files referencing the label or route |
| User documentation | 19 references to `/api/v1/servers` across 5 pages, plus `deploy/seed.yaml` |
| Payload fields | `server_name`, `server_id`, `server_url`, `server_info`, the metering context's `server`, the audit record's `server_name` |
| Environment variables | none |

## Decision drivers

- One name for one thing, chosen for what the thing is relative to the gateway, not for its history
  (design-principles §1).
- Make the change while it is cheap, rather than carrying aliases for a transition no one needs.
- Generated clients and new documentation learn only the new names.
- Contracts that are versioned on their own (the metering hook) are not changed as a side effect.

## Decision

- **Name.** *Upstream server*, *upstream* for short: the position of the resource relative to the gateway, which is
  the property that tells it apart from the gateway itself. On the wire it is always the short form: `upstreams` in
  paths, the OpenAPI tag and JSON and YAML keys, `/upstreams` for UI routes. Prose and UI titles say *upstream
  server*; the documentation introduces the term as "upstream server (upstream for short)" and uses either afterwards,
  so the wire name is one a reader has already met ([UPS-16](../../openspec/specs/upstreams/spec.md),
  [UI-7](../../openspec/specs/admin-ui/spec.md)).
- **Scope.** Collection nouns only: route paths, document keys, the tag, UI copy and routes. Payload field names stay
  (`server_name` on a tool or an audit record is already qualified by its object), and so do Python class names; both
  can follow later without touching the published contract.
- **No transition.** The old names go in one step: `/api/v1/servers` answers `404`, the admin UI's `/servers` pages
  are gone, and a bootstrap document that still says `servers` is rejected. The bootstrap document and its bundle
  entries now refuse unknown keys, so an outdated document fails at startup instead of quietly provisioning nothing
  ([MGMT-15](../../openspec/specs/management/spec.md)).

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
- **Keep the old names as deprecated aliases for a window.** Old routes answering with `Deprecation` and `Sunset`
  headers, the old bootstrap key accepted with a warning, old UI routes redirecting. It protects callers who exist; with
  none yet, it is an alias layer, tests and a removal date to maintain for nobody. A later rename of a surface that is
  in use should take this route.

## Consequences

**Positive:**

- A reader new to MCP never has to guess which "server" a page or a route means.
- No alias layer to carry and later remove.
- A misspelt or outdated bootstrap key now fails loudly, which it did not before.

**Trade-offs:**

- Anything written against the old names — scripts, a bootstrap file, a bookmark — breaks on upgrade and must be
  updated by hand. Acceptable only because nothing such exists yet.
- Payload fields keep the short `server_*` names, so the rename is visible in paths and keys but not inside bodies.
