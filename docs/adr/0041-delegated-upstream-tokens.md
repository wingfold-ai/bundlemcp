# ADR-0041: Delegated tokens replace token passthrough for identity-aware upstreams

**Status:** accepted · **Date:** 2026-09-24 · **Amends:** spec 24 (FWD-4)

## Context

Upstreams that must verify who is calling (the reference stack's `seo-gsc`)
are registered with `forward_headers: {"authorization": "authorization"}`:
the gateway passes the caller's own bearer, issued for a gateway endpoint,
and the upstream introspects it. The MCP authorization spec forbids this
("The MCP server MUST NOT pass through the token it received from the MCP
client"; servers "MUST NOT accept or transit any other tokens"): the upstream
holds a credential that opens the caller's endpoint, and the token's audience
is not the upstream.

Gateways that address this (agentgateway, Kong, Envoy AI Gateway) exchange
the caller's token for one issued to the upstream (RFC 8693 or Entra OBO).
bundlemcp is itself the authorization server of the caller's token and the
introspection authority its upstreams already use, so it can perform that
exchange without a third party.

## Decision drivers

- The upstream must be able to verify the caller without holding the
  caller's credential.
- Keep the existing introspection contract (FWD-4, OAS-5) so an upstream
  changes as little as possible.
- No Postgres schema change; no state a request depends on outside
  Valkey/Postgres (spec 30).

## Decision

- New `auth_mode: delegated_token`. For every upstream request the gateway
  mints a token (`bmcp_dt_…`) for the caller: subject = the caller's `sub`
  (user id or `api_key:<id>`), audience = the server's URL, actor = the
  endpoint the call came through, lifetime five minutes. Only its SHA-256
  hash is stored, in Valkey with a matching TTL, so any replica can
  introspect it and a restart invalidates nothing.
- Introspection recognises it first and reports `active`, `sub`, `email`,
  `aud` (the server URL), `token_use: delegated`, `act.sub`
  (`endpoint:<name>`) and the delegation client id.
- Anonymous callers get no token. Tool discovery, which has no caller, sends
  the server's static headers as for any other server.
- Forwarding `authorization` stays supported for existing trusted upstreams
  but is reported (`forwards_caller_token`) and labelled in the UI as
  passthrough, with `delegated_token` as the recommended alternative. The
  reference stack's `seo-gsc` keeps its configuration until its introspection
  code accepts the delegated `aud`.

## Alternatives considered

- **RFC 8693 at the gateway's token endpoint, called by the upstream.** Adds
  a round trip and client authentication per call for the same result.
- **Exchange at the upstream's own authorization server.** Requires every
  upstream IdP to trust bundlemcp as a subject-token issuer; out of scope
  (spec 24).
- **Signed JWT identity assertions.** Verifiable offline, but needs key
  distribution and rotation for every upstream; introspection is already in
  place.
- **Cache one delegated token per (caller, server).** Saves a Valkey write
  per call but means keeping the token value retrievable; minting per call
  keeps only hashes.

## Consequences

### Positive

- An upstream verifies callers with a token that is useless anywhere else.
- Upstreams already written for introspection need one extra check (`aud`).

### Trade-offs

- One Valkey write per upstream call for a delegated server, and one read
  per introspection.
- Introspection is on the hot path of every such call, as with forwarded
  bearers today.
