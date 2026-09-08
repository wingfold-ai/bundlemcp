# ADR-0024: Value objects for what crosses the edge; behavior on the entities that own it

**Status:** accepted · **Date:** 2026-09-03 · **Amends:** [ADR-0003](0003-sqlmodel-pydantic-first.md)

## Context

The repository rule is "Pydantic everywhere", yet the busiest paths passed
tuples and dicts: authentication returned a four-tuple read as `auth[1]` and
`auth[3]`; timeouts were a `tuple[float, bool, float]`; six service methods
and their routes returned `dict`, so those endpoints shipped as `object` in
the OpenAPI document and the generated TypeScript client. Entities were pure
column declarations, so their rules lived in helpers and were written more
than once: the presented-name rule three times, "server needs a per-user token"
four times, token expiry five times, with a naive-datetime fix-up duplicated
beside it. Enum-valued columns were typed `str`, so comparisons used literals.

## Decision drivers

- A tuple hides its meaning at every use site; a model states it once.
- A rule on the entity that owns it cannot drift between its copies.
- Typed columns turn a misspelled literal into an error at the boundary.
- Response models are what the web app's generated client is promised.

## Decision

- **Value objects.** `CallerIdentity` (auth method, user, email, key) replaces
  the tuple and is embedded on `SessionRecord`; `CallTimeouts` and
  `PresentedName` replace the remaining tuples and string-building. Every
  service method and every route returns a DTO; the dict-returning endpoints
  gained `BundleMembershipRead`, `ToolCurationRead`, `UpstreamOAuthClientRead`,
  `UpstreamOAuthStatusRead`, `UpstreamConnectionStatus`, `ConfigEntryRead` and
  `EndpointProfileRead`. `DiscoveryResult` moves to `schemas/`, where a
  published result belongs.
- **Entities carry their own facts.** `McpServer.requires_per_user_token`,
  `Endpoint.is_anonymous_only`, `ApiKey.reaches(endpoint_id)`,
  `OAuthAccessToken.is_usable`, `OAuthAuthorizationCode.is_redeemable`,
  `UpstreamOAuthToken.expires_within(skew)` and their siblings are properties
  on the SQLModel classes. Enum-valued columns are declared with their
  `StrEnum` types and stored as varchar through `sa_type=String`, so the
  schema is unchanged.
- **Timestamps are aware by type.** `UtcDateTime`, a SQLAlchemy type
  decorator, attaches UTC on read so no caller repairs naive datetimes.
- **Read DTOs are built by `from_entity`.** `EntityRead` is the base; a DTO
  whose shape differs from its entity (withheld header values) overrides it.
- **Names are types.** `ServerName`, `EndpointName` and `ResourceName` carry
  the validation once, for DTO fields and for renames alike, instead of
  constructing a throwaway upsert DTO to validate a rename.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- The OpenAPI document describes every response; the TypeScript client no
  longer receives `object` for six endpoints.
- Five duplicated rules exist once each.

### Trade-offs

- `SessionRecord` changed shape; its version is bumped, so sessions opened
  by the previous release read as expired and clients re-initialize once.
- Naive datetimes in the store are now interpreted as UTC on every backend.

