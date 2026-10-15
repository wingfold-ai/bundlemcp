# ADR-0049: Browser origins are an endpoint setting, not an auth mode

**Status:** accepted · **Date:** 2026-10-15

## Context

SEC-5 made every MCP endpoint answer CORS for any origin, without credentials, so browser-based MCP clients work. For
an endpoint that needs a credential that adds no access: a page can only present tokens it already holds. For an
open endpoint (`auth_modes: [none]`) it does. A website a visitor opens can drive the visitor's browser against an
endpoint the visitor can reach and the website cannot, such as a gateway on a company network, and read the answers.
That is the cross-site and DNS-rebinding case the MCP Streamable HTTP transport asks servers to defend against by
validating `Origin`.

## Decision drivers

- Authenticated endpoints must keep working for browser clients on any site.
- An open endpoint must not be usable by arbitrary websites through a visitor's browser.
- An operator must not mistake a browser policy for access control.

## Decision

- **Each endpoint carries `allowed_origins`**: origins whose pages may use it from another site, or `*` for any. The
  default is `[]` for an open endpoint and `*` for every other, which keeps the behaviour authenticated endpoints had.
- **The MCP edge decides per request**, after the endpoint lookup and before any credential is read. A request whose
  `Origin` is listed, or is the gateway's own, gets CORS on every response; any other `Origin` gets `403`; a request
  without an `Origin` is not affected. Preflights get an `OPTIONS` route answered from the same list.
- **It is not an auth mode.** `Origin` is reliable only from browsers; any other client sends what it likes. Listing it
  beside `oauth` and `api_key` would suggest it restricts who can call an endpoint, when it only restricts which web
  pages can make a browser call it.

## Alternatives considered

- **A new auth mode, "none, but only from these origins".** Reads as access control and is not: an open endpoint with
  that mode stays open to every non-browser client.
- **One global origin list for every MCP endpoint.** Simpler, but an operator with one open endpoint for their own web
  app and several authenticated ones for any client could not express both.
- **Keep the CORS decision in middleware, fed by a per-replica cache of endpoint origins.** Would put a CORS grant on
  responses given before the endpoint is resolved, at the cost of a second copy of endpoint state kept consistent by
  invalidation events.

## Consequences

### Positive

- Open endpoints are safe from cross-site use by default; listing an origin is the one step to allow a web app.
- The `Origin` check runs before authentication, so a refused page learns nothing about credentials.

### Trade-offs

- Responses given before the endpoint is resolved (unknown endpoint, a parse error, a body over the size limit) carry
  no CORS grant, so a browser on another site sees them as network errors.
- A preflight now reads the endpoint from the database; browsers cache the answer for ten minutes.
- A browser client of an open endpoint on another site stops working on upgrade until its origin is listed.
