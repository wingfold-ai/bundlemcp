# Design

## Context

See [proposal.md](proposal.md). The current code works as follows:

- `MetadataDocumentClientSource` (application, `application/oauth_server/`) resolves an `https://` client id through
  the `ClientMetadataFetcher` contract.
- `HttpxClientMetadataFetcher` (infrastructure, `infrastructure/httpx/client_metadata_fetcher.py`) is the adapter:
  - It caches a valid document in Valkey under `bmcp:cimd:{sha256(url)}`.
  - It calls `check_url_allowed` for an early refusal.
  - It fetches through `guarded_client(settings, timeout=10, follow_redirects=False)` and parses `response.json()`.
- The egress policy (`infrastructure/egress/`, ADR-0032, ADR-0048) works like this:
  - It is one function, `judge_address(addr, target, settings)`.
  - It is applied by `GuardedNetworkBackend` to the address actually dialled.
  - It allows RFC 1918 by default.

## Goals / Non-Goals

**Goals:**

- No caller can reach a non-public address through a metadata-document fetch, including through DNS rebinding.
- One fetch costs at most 16 KiB of memory and 5 seconds, and a failing URL costs one fetch per minute.
- Operators who do not need metadata-document clients can turn the feature off completely.

**Non-Goals:**

- Caps on the upstream OAuth discovery and registration reads (audit N3). Those requests are started by authenticated
  users; they can reuse the bounded reader later.
- Deduplicating concurrent first fetches of the same URL (a single-flight lock). The negative cache and the caps bound
  the cost enough.

## Decisions

### An egress scope, judged at connect time, rather than a pre-check

`judge_address` gains a `scope: EgressScope` parameter (an enum in `infrastructure/egress/`): `UPSTREAM` (today's
policy, the default) and `PUBLIC`. `PUBLIC` applies the full `UPSTREAM` policy first. It then also refuses any address
whose normalised form has `is_global == False`. That covers RFC 1918, CGNAT `100.64.0.0/10`, ULA `fc00::/7` and the
documentation ranges. IANA marks the NAT64 well-known prefix `64:ff9b::/96` as globally reachable, so `is_global`
alone would let `64:ff9b::a9fe:a9fe` (169.254.169.254) through. `PUBLIC` therefore also requires the IPv4 address
embedded in a NAT64 `64:ff9b::/96` address to be global. 6to4 `2002::/16` is already not global, so it is refused
outright. This closes the audit's N4 gap for this
path. An explicit allow CIDR still wins first, as it does today.

`guarded_client(settings, *, scope=EgressScope.UPSTREAM, **options)` passes the scope to `GuardedNetworkBackend`, so the
rule binds the address actually dialled. `check_url_allowed` takes the same scope for its early, clearer refusal.

Alternatives considered:

- **Check only in the fetcher, before connecting.** That is open to DNS rebinding, which is exactly what ADR-0048 moved
  the policy to connect time to prevent.
- **Tighten SEC-2's default for everyone.** That breaks the compose-network upstreams the default exists for.

ADR-0060, which extends ADR-0048, records the decision: unauthenticated, remote-chosen URLs use the `PUBLIC` scope. This
is the first exception to "one egress policy", so it gets a decision record.

### Bounded streamed read in the fetcher

The fetch runs under `asyncio.timeout(5)` and uses `client.stream("GET", ...)`. It first refuses a declared
`Content-Length` over 16 KiB. It then accumulates `aiter_bytes()` and aborts once the total passes 16 KiB, and parses
with `json.loads`, then `ClientIdMetadataDocument.model_validate`. The two steps keep today's distinction: a body that
is not JSON is a document that could not be fetched, and JSON that does not validate is an invalid document. The httpx
`timeout` drops to 5 s per phase as well, so connect stalls end early.

Why 16 KiB: real documents (claude.ai, ChatGPT, VS Code) are under 2 KiB, and the cap leaves room for long
`redirect_uris` lists. The constants live in the fetcher module, beside `MAX_TTL`. They are not settings: no operator
has a reason to raise them, and a setting would be one more knob to document.

### Negative cache in the same key family

On any `InvalidInputError` path the fetcher writes `bmcp:cimd:fail:{digest}` with `ex=60` and the failure kind
(`unreachable` or `invalid`). Before fetching, it checks this key and re-raises the same kind, so a cached failure is
reported exactly like a fresh one. The kind is stored as a small Pydantic model,
`CachedFetchFailure`, which follows the boundary round-trip rule.

### The switch lives in the application layer

`Settings.client_metadata_documents_enabled: bool = Field(default=True, ...)`. When it is false:

- The composition root does not register `MetadataDocumentClientSource`, so an `https://` client id falls through to
  "unknown client" and the fetcher is never called.
- The metadata DTO builder sets `client_id_metadata_document_supported` from the same setting.

Not registering the source, rather than putting a guard inside it, keeps the "off" state free of a branch on the hot
path.

## Risks / Trade-offs

- [A self-hosted client that publishes its document on a private address stops working] → it needs an allow CIDR.
  This is documented, and the refusal names "could not be fetched", the same as today.
- [A legitimate document larger than 16 KiB] → no known client is near the cap. The refusal is logged with the URL's
  host, so an operator can see it.
- [`is_global` differs between Python versions for edge ranges] → the tests pin the ranges that matter (RFC 1918,
  CGNAT, ULA, NAT64, 6to4, documentation), so a change in the standard library shows up as a test failure.

## Migration Plan

No data migration. Old positive cache entries stay valid. Deploy, then rollback is the previous image. Operators who
want the feature off set the new variable.
