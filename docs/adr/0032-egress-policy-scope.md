# ADR-0032: The egress policy governs every outbound URL, not only MCP transport

**Status:** accepted · **Date:** 2026-09-06 · **Extends:** [ADR-0017](0017-upstream-oauth-encryption.md)

## Context

`check_url_allowed` implemented SEC-1 and SEC-2 but was applied at exactly one call site, the upstream MCP client
factory. The upstream OAuth path made three outbound requests without it: the discovery probe against the server's
origin, the follow-up to the authorization server that the server's protected-resource document named, and the token
request to the endpoint that server's metadata named. The last two URLs are chosen by the remote side, and the token
request carries the gateway's pre-registered client secret. A compromised upstream could name an attacker's host and
receive the secret, or name a metadata service address and use the gateway as a proxy.

The OIDC relying party made the same requests, against operator-configured URLs, and the client-metadata fetcher for
OAS-13 was written with the check from the start.

## Decision drivers

- One gate is auditable; two gates that disagree are not.
- The URLs a remote party names are the dangerous ones, and they were the unchecked ones.

## Decision

- Every outbound HTTP request the gateway initiates passes the egress policy before it is made, whether the URL came
  from an administrator, an operator or a remote document. `HttpxUpstreamProvider` checks the server origin, the named
  authorization server and the token endpoint; `JoseOidcProvider` checks the discovery, token and JWKS URLs; the
  client-metadata fetcher already did.
- A refusal is reported in the vocabulary of the flow it interrupts (`NeedsConnect` with a reason for the upstream
  client, `OidcError` for the relying party), never as an unhandled exception.
- The providers take an `httpx.AsyncClient` factory so the chain is tested with a mock transport, including the
  assertion that a blocked URL is never requested.
- The egress policy is the one SSRF gate. A library that ships its own allowlist (FastMCP's client-metadata fetcher
  does) is not used for fetching; bundlemcp's fetcher goes through `check_url_allowed`.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- The upstream client secret cannot be redirected to a blocked address, and discovery cannot reach link-local or
  loopback ranges.
- Together with the issuer binding of UPO-8, an upstream that swaps its authorization server after the connect began is
  refused at the callback.

### Trade-offs

- An identity provider or upstream on the gateway's own loopback now needs an explicit `BUNDLEMCP_EGRESS_ALLOW_CIDRS`
  entry, which the settings description says.
- The check resolves DNS synchronously, as the MCP transport check already did; it runs once per flow step, not per tool
  call.

