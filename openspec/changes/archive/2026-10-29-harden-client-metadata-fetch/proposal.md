# Proposal

## Why

`GET /oauth/authorize?client_id=https://…` makes the gateway fetch that URL as a client ID metadata document (AUTH-13)
**before anyone signs in**. Three things make this an attack surface for anyone on the internet:

- **Private addresses are reachable.** The fetch goes through the default egress policy, which allows private RFC 1918
  ranges because compose-network upstreams need them (SEC-2). Any internet caller can therefore make the gateway send
  HTTPS GETs into its own network. The difference between a fast refusal and the 10-second timeout works as a
  port-scan oracle.
- **The body is unbounded.** It is read with no size cap, and the timeout applies per read, so a slow endless response
  holds memory and a worker for as long as the attacker likes.
- **Failures are not cached.** Every request pays for a full fetch.

The 2026-10-29 code audit found this (finding M3).

## What Changes

- **Metadata documents are fetched from public addresses only** (AUTH-13, modified). On top of the egress policy, a
  metadata-document fetch refuses any address that is not globally routable: private, loopback, link-local, CGNAT,
  unique-local, documentation and translation ranges. An explicit `BUNDLEMCP_EGRESS_ALLOW_CIDRS` entry still wins,
  so a test or air-gapped setup can allow a known host.
- **Bounded fetch** (AUTH-13, modified):
  - The body is read as a stream and refused beyond 16 KiB.
  - The whole fetch has a 5-second deadline, not a per-read timeout.
  - A failed or invalid fetch is cached for 60 seconds, so repeated requests for the same URL do not refetch.
- **Operators can turn metadata-document clients off** (AUTH-34, added). A new setting,
  `BUNDLEMCP_CLIENT_METADATA_DOCUMENTS_ENABLED` (default `true`), controls it. When it is off, the authorization
  server metadata advertises `client_id_metadata_document_supported: false`, and an `https://` `client_id` is refused
  as an unknown client without any fetch.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: AUTH-13 (public-only, bounded, failure-cached fetch) and AUTH-34 (added: the switch to turn
  metadata-document clients off).

## Impact

- **Resolves:** audit finding M3 (2026-10-29). No GitHub issue.
- **Code:**
  - `infrastructure/egress/`: a public-only egress scope, judged at connect time like the default one.
  - `infrastructure/httpx/client_metadata_fetcher.py`: streamed, capped and deadline-bound reads, plus a negative
    cache key.
  - `application/settings/settings.py`: the new setting.
  - `application/oauth_server/`: the source refuses when the setting is off, and the metadata advertisement follows
    it.
  - `main/composition_root.py`: wiring.
- **API:** the setting changes the value of `client_id_metadata_document_supported` in
  `/.well-known/oauth-authorization-server`, but the DTO shape is unchanged. Re-run `npm run openapi` anyway, to
  confirm that nothing drifted.
- **Behaviour:** a metadata document hosted on a private address stops working unless that address is explicitly
  allowed. Real clients (claude.ai, ChatGPT) host theirs publicly.
- **Docs:**
  - A new ADR, ADR-0060 "Unauthenticated fetches use a public-only egress scope", which extends
    ADR-0048.
  - `docs/self-hosting/configuration.md` (the new setting).
  - `docs/integrate/http-surface.md` (client registration).
  - arc42 §8 (egress).
- **Not covered:** the same caps for upstream OAuth discovery (audit N3). That fetch is started by an authenticated
  user, so it is a separate, lower-priority change.
