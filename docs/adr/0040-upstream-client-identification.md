# ADR-0040: The gateway identifies itself upstream in the MCP spec's order

**Status:** accepted · **Date:** 2026-09-24 · **Amends:** [ADR-0017](0017-upstream-oauth-encryption.md)

## Context

The upstream OAuth client (`HttpxUpstreamProvider`) was written against the 2025-06-18 authorization spec. Checked
against revisions 2025-11-25 and 2026-07-28 it fell short in ways that block or weaken real connects:

- Client registration was pre-registered or dynamic registration (DCR) only. Since 2025-11-25 the priority is
  pre-registered → Client ID Metadata Document (CIMD) → DCR → ask the user, and 2026-07-28 deprecates DCR.
- The RFC 8707 `resource` parameter, which clients "MUST send … regardless of whether authorization servers support it",
  was never sent.
- The challenge was requested with `GET`; a 2026 stateless server answers `GET` with 405 before any authorization check.
- Metadata without PKCE support was not refused; the metadata's `issuer` was not checked against the one it was fetched
  for; DCR requests lacked the now-required `application_type`; a registration survived the server moving to another
  authorization server.
- A 403 `insufficient_scope` step-up challenge was not handled.
- A shared server authorizing a machine had no non-interactive path, though the OAuth Client Credentials extension is
  final.

The SDK's `OAuthClientProvider` implements most of this, but it is built for an interactive single-user client that owns
the redirect and holds tokens in memory, while the gateway runs the redirect as a web route, stores tokens per (server,
user) in Postgres, and refreshes single-flight across replicas.

## Decision drivers

- Conform to the current MCP authorization spec without changing how tokens are stored or refreshed.
- An admin-entered client is never replaced by the gateway.
- Every URL the remote side names still passes the egress policy.

## Decision

- **Identification order** (`UpstreamConnectFlow.ensure_client`): an admin-stored client; else, when the authorization
  server advertises `client_id_metadata_document_supported` and accepts public clients and the gateway is served over
  https, the gateway's own document at `/oauth/upstream/client.json` as client id; else DCR as a public `web` client;
  else "store a client". How a client was obtained is recorded in its metadata (`identification`).
- **Issuer binding.** A client the gateway obtained is bound to its issuer; a different issuer at connect time discards
  it and its tokens and obtains a new one. An admin-stored client bound to an issuer is refused against another.
- **Resource indicators** on authorization, token and refresh requests: the protected resource's `resource` when it
  covers the server URL, else the canonical server URL.
- **Refusals.** Metadata without `S256` PKCE, or naming another issuer than the one it was fetched for, is refused.
- **Challenge by POST** of a `server/discover` request with the 2026 headers.
- **Step-up.** A 403 `insufficient_scope` on a call records the challenged scopes (`step_up_scopes`) for the next
  connect and returns the reconnect error; it is not retried with a refreshed token, which would lack the scope too.
- **Client credentials.** An admin client may carry `grant_type: client_credentials` (shared servers only, secret
  required). Tokens are obtained with the grant on first use or on `POST …/upstream-oauth:connect`, and renewed by
  granting again, under the existing single-flight refresh lock. JWT client assertions are not supported.
- The hand-written provider stays; wrapping the SDK provider was evaluated and rejected (below).

## Alternatives considered

- **Wrap the SDK's `OAuthClientProvider`.** Would bring CIMD, `resource` and step-up for free, but it drives the
  redirect through callbacks in one process and keeps state in its own storage interface; adapting it to a browser round
  trip across replicas and per-user Postgres rows would cost more than the targeted changes and couple token storage to
  SDK internals.
- **Keep DCR as the default.** Deprecated by the 2026-07-28 spec, and providers are dropping it; CIMD needs no stored
  registration at all.
- **Retry a step-up with a refreshed token.** The refreshed token carries the same grant, so it fails the same way.

## Consequences

### Positive

- Connects work against authorization servers that only offer CIMD, and tokens are audience-bound to the server they are
  for.
- Moving a server to another authorization server heals on the next connect.
- Machine-to-machine upstreams need no interactive connect.

### Trade-offs

- CIMD needs a gateway served over https; plain-http development deployments fall back to DCR.
- The provider remains bundlemcp code that must follow future revisions; the spec test suite
  (`tests/infrastructure/test_upstream_provider.py`) pins each MUST it implements.
