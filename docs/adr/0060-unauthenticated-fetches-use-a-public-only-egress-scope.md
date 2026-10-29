# ADR-0060: Unauthenticated fetches use a public-only egress scope

**Status:** accepted · **Date:** 2026-10-29 · **Extends:** [ADR-0048](0048-egress-policy-enforced-at-connect-time.md)

## Context

ADR-0032 put every outbound request behind one egress policy, and ADR-0048 enforces it on the address actually dialled.
That policy allows private RFC 1918 ranges, because the upstreams an administrator registers usually live on the
compose or cluster network.

One outbound request is not chosen by an administrator. A client ID metadata document
([AUTH-13](../../openspec/specs/auth/spec.md)) is fetched from whatever `https://` URL a caller names as its
`client_id`, on the authorize endpoint, before anyone signs in. Under the shared policy, anyone on the internet could
make the gateway send GET requests into its private network and time the answers. The body was read whole, with a
per-read timeout only, so a slow endless response held a worker, and a failing URL was fetched again on every request.

## Decision drivers

- A URL an unauthenticated caller chooses must not reach anything the internet could not reach itself.
- The private-network default stays for registered upstreams, which need it.
- The refusal must bind the dialled address, as ADR-0048 requires, or DNS rebinding reopens the hole.

## Decision

- **An egress scope.** The policy takes an `EgressScope` (`infrastructure/egress/`). `UPSTREAM` is the policy as
  before. `PUBLIC` applies it and then also refuses every address that is not globally routable. For a NAT64
  `64:ff9b::/96` address, the IPv4 address it translates to must be globally routable as well. An explicit
  `BUNDLEMCP_EGRESS_ALLOW_CIDRS` entry still wins first, so a test or air-gapped setup can allow a known host.
- **The scope travels with the client.** `guarded_client(settings, scope=...)` hands it to the guarded network backend,
  so the check runs at connect time, on every dialled address. `check_url_allowed` takes the same scope for its early
  refusal.
- **The metadata-document fetcher uses `PUBLIC`.** It also streams the body with a 16 KiB cap, gives the whole fetch a
  5-second deadline, and remembers a failure for 60 seconds.
- **Operators can turn the feature off.** With `BUNDLEMCP_CLIENT_METADATA_DOCUMENTS_ENABLED=false`, the
  metadata-document client source is not registered, so an `https://` `client_id` is an unknown client and nothing is
  fetched ([AUTH-34](../../openspec/specs/auth/spec.md)).

## Alternatives considered

- **Check in the fetcher before connecting.** Open to DNS rebinding, which ADR-0048 closed.
- **Tighten the default policy for everyone.** Breaks the private-network upstreams the default exists for.
- **A separate, unguarded client with its own address check.** Two enforcement points that could drift apart.

## Consequences

### Positive

- An unauthenticated caller cannot use the gateway to probe its private network or cloud metadata.
- One fetch costs at most 16 KiB and 5 seconds; a failing URL costs one fetch a minute.

### Trade-offs

- A client that publishes its metadata document on a private address needs an allow entry.
- The upstream OAuth discovery reads are not yet capped the same way. They are started by an authenticated user, so
  they keep the `UPSTREAM` scope.
