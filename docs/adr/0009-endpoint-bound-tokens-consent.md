# ADR-0009: OAuth consent screen + endpoint-bound access tokens

**Status:** accepted · **Date:** 2026-07-02

## Context

The initial OAuth spec (like metamcp) had open dynamic client registration,
no consent step, and tokens valid on every OAuth endpoint. Adversarial review
flagged it: any registered client that walks a logged-in user through a
redirect obtains a token usable across all endpoints — an authorization hole
and a billing-attribution risk for the application layer.

## Decision

Two controls in [spec/20](../../spec/20-oauth-server.md):
**consent** (OAS-11 — per (user, client, endpoint), persistent, revocable)
and **endpoint-bound tokens** (OAS-10 — RFC 8707 resource indicators; the
token's audience is the endpoint; endpoints reject mismatches, EP-3a).

## Reasons

- Tokens ignoring endpoint identity contradicts the product's core concept
  (per-client endpoints).
- Consent is the standard OAuth answer to confused-deputy redirects; current
  MCP auth guidance expects resource indicators.
- Stable per-endpoint audience improves metering attribution for ultra-mcp.

## Consequences

- (+) A leaked/replayed token is confined to one endpoint; users see and can
  revoke what they granted.
- (−) One extra browser step on first connect per client+endpoint.
- (−) Clients must re-authorize per endpoint (that's the point); v1 keeps a
  single scope and uses audience — not scopes — for binding.
