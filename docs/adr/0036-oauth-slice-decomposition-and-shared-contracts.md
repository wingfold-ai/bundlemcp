# ADR-0036: The OAuth slice decomposes into resolution, consent and issuance; time, hashing and randomness become contracts

**Status:** accepted · **Date:** 2026-09-18 · **Amends:** [ADR-0028](0028-oauth-server-as-services.md),
[ADR-0014](0014-gateway-rendered-oauth-authlib.md)

## Context

[ADR-0028](0028-oauth-server-as-services.md) moved the OAuth authorization
server out of its controllers and into services with grant strategies. That was
the right direction and it left three problems behind.

**`AuthorizationService` had become the slice's second god object.** One class
resolved the client (two unrelated ways — an opaque registered id, or an
`https://` client ID metadata document it had to fetch and mirror), decided
whether standing consent covered the request, and minted authorization codes.
The three have different collaborators and different failure modes, and the
mirroring one had a bug the shape made easy: a pre-login `authorize` for a
document client committed a client row, so an unauthenticated request wrote to
the database.

**The protocol's vocabulary was string literals.** `"none"`, `"S256"`,
`"authorization_code"`, `"web"` and every error code were bare strings, guarded
in places by regex patterns on the registration DTO. Nothing typed them, so
nothing stopped a grant type being stored that the token endpoint would later
refuse — and a registration the server could not honour answered with FastAPI's
`422` validation shape rather than the `400 invalid_client_metadata` that
RFC 7591 §3.2.2 requires.

**The slice read the wall clock, hashed with a fixed scheme and drew randomness
inline.** `datetime.now(UTC)` and `sha256` appeared directly in services whose
behaviour is entirely about expiry and secrets. Testing "this token is refused
after an hour" therefore meant either sleeping or monkeypatching, and
`api/oauth/urls.py` spelled out the `{base}/{name}/mcp` resource identifier in
five places that could drift apart.

## Decision drivers

- A service whose name is a whole subsystem attracts every new rule; the
  resolution/consent/issuance split is the one the protocol itself makes.
- Illegal protocol values should be unrepresentable, and a refusal should be in
  the protocol's own error vocabulary, not the web framework's.
- Expiry and secret generation are the slice's core behaviour, so they must be
  directly testable without patching — the same argument ADR-0025 made for the
  `UnitOfWork`.
- One owner per fact (ADR-0024): a resource identifier with five spellings has
  no owner.

## Decision

**Decompose `AuthorizationService` into three collaborators it composes**, with
its public surface unchanged so controllers and providers did not move:

| Class | Owns |
|---|---|
| `ClientResolver` | Asks a chain of `ClientSource`s: `RegisteredClientSource` for opaque ids, `MetadataDocumentClientSource` for `https://` ids. A new way for a client to identify itself is one new source. |
| `ConsentService` | The standing-permission check and the grant of consent. |
| `AuthorizationCodeIssuer` | Minting codes and staging their hashes, mirroring `TokenIssuer`. |

`MetadataDocumentClientSource` only *stages* its mirror; `AuthorizationService`
commits it in `validate`, after login. The pre-login check now writes nothing.

**Type the protocol's vocabulary as domain enums** in `domain/oauth/`:
`GrantType`, `ResponseType`, `CodeChallengeMethod`, `TokenEndpointAuthMethod`,
`ApplicationType`, `OAuthErrorCode`. The registration DTO's regex patterns are
gone — the enums carry the legal values. `OAuthError` and
`AuthorizationRedirectError` take an `OAuthErrorCode` and derive the HTTP status
from it, so no caller passes a status. Registration failures answer per
RFC 7591 §3.2.2, which means the implicit grant is refused at registration
rather than stored and refused later (OAS-2).

**Put the rules on the entities that own them** (ADR-0024): `OAuthClient`
decides whether it is public, whether a presented secret is its own and which
grants it registered for; `OAuthAuthorizationCode` answers whether a redemption
names its client, repeats its redirect URI and proves its PKCE challenge;
`OAuthConsent` knows whether it still stands; `ClientIdMetadataDocument` checks
itself against the URL it was fetched from. Registered grant types are now
honoured at both endpoints (OAS-4).

**Introduce `Clock`, `SecretHasher` and `SecretGenerator`** as protocols in
`domain/shared/`, with their production implementations beside them
(`SystemClock`, `Sha256SecretHasher`, `OsSecretGenerator`) and fakes in
`infrastructure/memory/` (`ManualClock`, `SequentialSecretGenerator`). Expiry
predicates take the instant as an argument — hence `OAuthAccessToken`'s
`is_usable_at(now)` rather than an `is_usable` property. Token lifetimes become
the runtime-configurable values OAS-4 always promised, carried by a
`TokenPolicy` value object; the module-level lifetime constants are gone.

**`EndpointResource`** (`domain/endpoints/`) becomes the single owner of the
`{base}/{name}/mcp` identifier: it builds the resource URL and its RFC 9728
metadata URL and parses a `resource` parameter back. `api/oauth/urls.py` is
deleted.

The composition root lists the grants the token endpoint serves and the ways a
client may identify itself; the OAuth providers instantiate them per request.
Introspection moves to its own controller behind an `IntrospectionAuth` router
dependency (ADR-0026's policy-on-the-base-class rule).

## Alternatives considered

- **Leave `AuthorizationService` whole and extract only the metadata-document
  path.** Rejected: it fixes the write-before-login bug without addressing why
  three unrelated responsibilities shared a transaction boundary, and the next
  client-identification scheme would land in the same class.
- **`Literal["none", "S256", …]` instead of enums.** Rejected: a `Literal`
  types the value but has nowhere to hang behaviour, and these values do have
  behaviour — `CodeChallengeMethod` verifies a challenge, `OAuthErrorCode`
  carries an HTTP status.
- **`freezegun` (or monkeypatching `datetime`) instead of a `Clock` contract.**
  Rejected: it makes time testable without making it *visible*. A predicate
  that reads the clock internally cannot be reasoned about locally, and the
  patch is global to the test process. Passing the instant is one parameter and
  no magic.
- **Keep hashing concrete, since only SHA-256 is used.** Rejected on the same
  grounds as the clock: the point is a deterministic test double, not
  algorithm choice. `SecretHasher` wraps the primitives in `domain/shared/secrets.py`
  rather than replacing them.
- **One `oauth/` package spanning the layers.** Rejected: it would re-import
  the vertical-slice shape ADR-0033 removed. The slice's parts sit in the layer
  each belongs to, which is why the enums are in `domain/` and the sources in
  `application/`.

## Consequences

### Positive

- An unauthenticated `authorize` for a metadata-document client no longer
  writes a client row.
- A new client-identification scheme is one `ClientSource`, registered in the
  composition root; the resolver does not change.
- Illegal protocol values are unrepresentable, and every refusal the server
  emits is a member of `OAuthErrorCode` with its status attached.
- Expiry is directly testable: a test advances `ManualClock` past the access and
  refresh lifetimes and asserts each token is refused, with no patching and no
  sleeping. The code-issuer test asserts the exact value a deterministic
  generator produces.
- Token lifetimes are operator-tunable at runtime, closing the gap between
  OAS-4 and the code.
- One owner for the endpoint resource identifier, so the RFC 9728 metadata URL
  and the `resource` parameter cannot drift apart.

### Trade-offs

- **Three more classes and a protocol where there was one service.** Reading
  the authorize flow end to end now means four files. This is the cost of the
  split and it is paid on every read, not just on change.
- **Every service in the slice takes three more constructor arguments.** Auth,
  caller resolution, API keys, both issuers, both grants, token, introspection,
  registration and purge all receive `Clock`, `SecretHasher` and
  `SecretGenerator` from the composition root. The wiring in
  `main/composition_root.py` is correspondingly longer.
- **`is_usable_at(now)` is more verbose than `is_usable`** at every call site,
  and it is a breaking change to any code that read the property.
- **The enums are a migration hazard.** A value already stored in Postgres that
  is not an enum member now fails validation on read rather than being passed
  through. This is intended, but it means an enum can only be narrowed with a
  data migration.
