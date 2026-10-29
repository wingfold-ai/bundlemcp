# Design

## Context

See [proposal.md](proposal.md). The current code, per finding:

- **Login (S1).**
  - `LoginController.login` (`api/oauth/controllers/login_controller.py:42-70`) parks an `OidcLoginState` (nonce,
    PKCE verifier, `next_url`) in a `ValkeySingleUseState` under the `state` token, with a 600-second TTL
    (`BROWSER_STATE_TTL`, `main/composition_root.py:122`). It then redirects to the identity provider.
  - `login_callback` (`:72-122`) calls `states.take(state)` (`:85`), exchanges the code, provisions the user and sets
    the session cookie. Nothing ties the callback to the browser that called `/login`.
  - The session cookie's attributes come from `session_cookie_kwargs` (`api/oauth/session_cookie.py:6-14`): `HttpOnly`,
    `SameSite=Lax` and `Path=/`, with `Secure` passed in as `settings.public_base.startswith("https")`
    (`login_controller.py:118`).
- **Body limit (S2).**
  - `RequestBodyLimit` (`api/http/request_body_limit.py:49-88`) is ASGI middleware mounted in `main/app.py:95`. It
    returns early for any path that matches neither `API_PATH` nor `MCP_PATH` (`:58`). Its limit comes from the
    runtime-config snapshot (`:54`), and `too_large` (`:38-46`) renders a JSON-RPC or `{"detail"}` body.
  - The unauthenticated routes that read a body are `POST /oauth/register`, `/oauth/token`, `/oauth/revoke`,
    `/oauth/introspect` and `/oauth/consent`. All of them live under the `/oauth` prefix.
  - `registration_body` (`api/oauth/registration_body.py:23`) calls `request.json()`.
  - `ClientRegistrationRequest` (`application/schemas/oauth/client_registration_request.py`) bounds only
    `redirect_uris` from below (`min_length=1`).
- **Static headers (S3).**
  - `McpServerRow.static_headers` (`infrastructure/postgres/rows/mcp_server_row.py:29-33`) is a plain `JSON` column.
  - Rows map to and from the `McpServer` entity generically (`infrastructure/postgres/sqlalchemy_repository.py:41-45`),
    and staged entities are written with `session.merge` (`:47-51`).
  - Consumers read the plaintext `McpServer.static_headers` directly:
    - `infrastructure/fastmcp/client_factory.py:75,99,123`;
    - `application/management/config_export_service.py:81`;
    - `application/inspection/inspector_service.py:323`;
    - `application/discovery/discovery_service.py:298`.
  - Encryption today is applied by application services through the `SecretCipher` contract
    (`application/contracts/secret_cipher.py`) onto `*_encrypted` entity fields.
  - The cipher is optional. `_build_cipher` (`main/composition_root.py:494-499`) returns `None` without keys, and the
    unit-of-work factory is built at `:186`, before the cipher at `:193`.
  - `SecretReencryption` (`application/upstream_oauth/secret_reencryption.py`) pages two tables through a
    `StoredSecrets` protocol (`:18-23`): `page_after`, and a compare-and-set `replace_ciphertext`. It skips values
    already under the primary key (`:71`).
  - `SecretReencryptionJob` runs `SecretReencryption` only when a cipher exists and the interval is non-zero
    (`composition_root.py:359`). It sleeps one interval before its first pass
    (`api/jobs/secret_reencryption_job.py:57-63`).
  - Migrations run before the gateway starts (`apps/gateway/Dockerfile:42`). The latest is `0016_member_listings`.

## Goals / Non-Goals

**Goals:**

- A login callback finishes only in the browser that started that login, with no new database or Valkey round trip
  on the refusal path.
- No unauthenticated request makes the gateway buffer more than 64 KiB, and no registration stores unbounded
  metadata.
- With a key configured, no static header value is at rest in plaintext once one background pass has run. Every
  consumer of `McpServer.static_headers` stays unchanged.
- A keyless deployment keeps working, and an operator can see that it stores plaintext.

**Non-Goals:**

- Binding the OAuth authorize flow or the upstream-connect flow to the browser. Both need a gateway session already,
  and UPS-27 binds the connect callback to the session user.
- A `Content-Type` check on any surface.
- Encrypting `forward_headers`. That column holds header names only, never values.
- Dropping the plaintext `static_headers` column. A keyless gateway still stores there.

## Decisions

### Login binding: a random value in a cookie, its hash in the state

`/login` generates `binding = secrets.token_urlsafe(32)` and stores `hash_token(binding)`
(`domain/shared/secrets.py`) in a new required `OidcLoginState.browser_binding_hash` field. It sets the binding cookie
on the redirect response.

The callback works in order of increasing cost:

1. It reads the cookie, which costs no I/O. With no cookie, it answers `400` and touches nothing in Valkey.
2. It calls `states.take(state)`.
3. It compares the hashes with `tokens_equal` (constant time). On a mismatch it answers `400`. The state is already
   consumed by then.

Only after that does the callback check the provider and the IdP `error`, and exchange the code. Every callback
response expires the cookie, whether it succeeds or not.

Cookie attributes (a new `api/oauth/login_binding_cookie.py`, beside `session_cookie.py`, in the api layer):

- Name `__Host-bmcp_login` when `public_base` is https, otherwise `bmcp_login`. Browsers refuse a `__Host-` cookie
  without `Secure`, and a plain-http compose deployment on a non-localhost host cannot set `Secure` cookies.
- `HttpOnly`, `SameSite=Lax`, `Path=/`, no `Domain`, and `max_age=600`, so it lives exactly as long as the Valkey
  state. `SameSite=Lax` is enough because the IdP returns the browser with a top-level GET.
- The module exposes `login_binding_cookie_name(secure)` and `login_binding_cookie_kwargs(secure)`. This mirrors
  `session_cookie_kwargs`, so `Secure` is derived from the public URL in the same way (DEP-1).
- `BROWSER_STATE_TTL` moves from `main/composition_root.py` into `api/oauth/browser_state/`, where both the state
  store wiring and the cookie module read it. It is the lifetime of browser round-trip state, and the composition
  root keeps importing it from there.

Alternatives considered:

- **Cookie carrying `sha256(state)`**, as the audit suggested. The state appears in the IdP's URLs, its logs and the
  browser history, so anyone who sees it can compute the cookie value. Only the `__Host-` prefix would keep an
  attacker from planting it. A random value also holds on plain-http deployments.
- **Binding the login to the existing session cookie.** A login usually starts with no session, so there is nothing
  to bind to.
- **One cookie per login, named by a state digest**, so that parallel logins in two tabs both succeed. This leaves
  more cookies behind. Parallel admin logins are rare, and the losing tab shows "start again".

### `/oauth/` gets its own fixed limit in the same middleware

`RequestBodyLimit` learns a third path family, `OAUTH_PATH = re.compile(r"^/oauth(/|$)")`, with a fixed
`OAUTH_BODY_LIMIT = 64 * 1024` that lives beside it in the module. `_limit_for(path, scope)` returns the fixed limit
for OAuth paths and the runtime limit otherwise. `too_large` gains a third shape for OAuth paths:
`{"error": "invalid_request", "error_description": "request body exceeds the 65536-byte limit"}`. RFC 6749 clients
parse this shape. The streaming count, the `BodyTooLarge` path and `body_too_large_handler` are reused unchanged.

Why fixed and not a setting: real requests to these routes are under 4 KiB, and no operator has a reason to raise the
limit. 64 KiB is also the lower bound SEC-7 sets for the configurable limits.

Alternatives considered:

- **Apply the runtime 4 MiB limit to `/oauth/` too.** That is simpler, but it lets an anonymous caller parse 4 MiB of
  JSON per request.
- **Cap the read inside `registration_body`.** That covers one route only. The form-parsed token, revoke, introspect
  and consent routes would stay unbounded.

### Registration bounds in the DTO

`ClientRegistrationRequest` gains declarative constraints, so they reach the JSON schema and fail at parse time
(pydantic-fields.md):

- `redirect_uris: list[Annotated[str, Field(max_length=2048)]] = Field(min_length=1, max_length=10, …)`;
- `client_name` with `max_length=200`, and `scope` with `max_length=1000`;
- `grant_types` and `response_types` with `max_length=10`.

`registration_body` already turns any `ValidationError` into `invalid_client_metadata` naming the field
(`registration_body.py:28-35`), so it needs no change. The descriptions gain the bound in words, because they are
published API surface.

### Static headers: encrypted transparently in the repository adapter

This is a new pattern: an infrastructure adapter encrypts a field, where until now application services did. The
decision is recorded as ADR-0061, which amends ADR-0017.

- **Infrastructure.**
  - `McpServerRow` gains `static_headers_encrypted: str | None`, a `Text` column. It holds one Fernet token of the
    canonical JSON of the whole header dict (sorted keys).
  - `SqlAlchemyServerRepository` takes `cipher: SecretCipher | None` and overrides `_to_row` and `_to_entity`:
    - **With a cipher, on write:** a non-empty dict is encrypted into `static_headers_encrypted`, and
      `static_headers` is set to `{}`.
    - **With a cipher, on read:** the ciphertext is decrypted. A row that still has plaintext and no ciphertext is
      read from the plaintext column.
    - **Without a cipher:** the plaintext column is read and written as today.
    - **Undecryptable values:** if no key decrypts a value, or a row holds ciphertext but there is no cipher, the
      entity gets `{}` and the read logs `server.static_headers_undecryptable` with the server id. The repository
      remembers that id for the unit of work. A later write of the same entity with an empty dict keeps the stored
      ciphertext instead of clearing it (ARC-18 scenario). Without this, an unrelated edit would destroy a value that
      a restored key could still decrypt.
  - `SqlAlchemyUnitOfWork` and `SqlAlchemyUnitOfWorkFactory` take the optional cipher and pass it to the server
    repository. `CompositionRoot` builds the cipher before the factory.
- **Application.**
  - `StoredSecrets` moves from `application/upstream_oauth/secret_reencryption.py` to
    `application/contracts/persistence/stored_secrets.py`, unchanged, because a repository contract now names it.
  - `ServerRepository` gains two methods:
    - `header_ciphertexts() -> StoredSecrets`, a view over `(id, static_headers_encrypted)` whose
      `replace_ciphertext` is a compare-and-set on that column;
    - `seal_plaintext_headers(limit: int) -> int`, which encrypts up to `limit` rows still holding plaintext and no
      ciphertext, each guarded by `static_headers_encrypted IS NULL`, and returns how many it sealed (0 without a
      cipher).
  - `SecretReencryption.sweep` first seals in batches until a batch seals fewer than `BATCH_SIZE`. It then runs its
    existing `_sweep` over a third table, `lambda uow: uow.servers.header_ciphertexts()`.
  - `ReencryptionSweep` gains a `sealed` counter, and the job's `token_encryption.swept` log line carries it.
- **In-memory fakes.** `InMemoryServerRepository` keeps plaintext entities. Its `header_ciphertexts()` returns an
  empty view and `seal_plaintext_headers` returns 0, so application tests are unaffected. Encryption is verified
  against sqlite in `tests/infrastructure/`.
- **Startup warning.** After migrations, `CompositionRoot` counts the servers with non-empty plaintext headers through
  a third repository method, `count_plaintext_headers()`. When the count is non-zero it logs
  `static_headers.plaintext` at WARNING with `servers=<n>` and `reason` set to `no_encryption_key` or
  `awaiting_reencryption_pass`. The log carries no names or values (SEC-10).
- **Migration `0017_encrypted_static_headers`.** It adds the nullable column and nothing else. Downgrade drops the
  column, which loses encrypted headers. The ADR and the migration docstring say so.

The plaintext is moved at runtime, not in the migration. Only the gateway loads `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS`
through `Settings` with all its sources, and the sweep has to seal rows anyway: keys can be added after the
migration has run, and a previous-release replica keeps writing plaintext during a rolling deploy. Sealing in the
first sweep, one interval after start, also leaves a rolling deploy time to finish before any existing row's
plaintext column is cleared. Old replicas read only that column.

Alternatives considered:

- **Encrypt in the application services, like client secrets.** `McpServer` would carry
  `static_headers_encrypted`, and every consumer would need the cipher to decrypt: the upstream client factory, the
  inspector, discovery, and export. That is four call sites and a contract dependency in infrastructure code that has
  none today, all to reach plaintext they use as is.
- **Encrypt each value in the JSON column**, as `{"Authorization": "<fernet>"}`. Header names would stay readable
  when a key is lost. But compare-and-set needs JSON equality, and the Postgres `json` type has none. It would also
  mix plaintext and ciphertext in one column, told apart only by a prefix.
- **Encrypt in the Alembic migration with keys read from the environment.** That only works when the keys are in
  the migration's environment. It is a second implementation of sealing, and it clears plaintext while
  previous-release replicas still read it.
- **Refuse static headers without a key**, the ADR-0017 stance for upstream OAuth. Every keyless deployment that has
  a static-header server today would break on upgrade. See Open Questions.

## Risks / Trade-offs

- [A login started on a previous-release replica has no `browser_binding_hash`, so its state fails validation and
  `take` returns `None`] → the callback answers "invalid or expired state" and the user starts again. This affects
  logins in flight during the deploy only, for at most 10 minutes.
- [Two logins in parallel in one browser: only the latest finishes] → the earlier tab gets `400` and starts again.
  This is documented in the http-surface page.
- [A server edited on a new replica during a rolling deploy has an empty plaintext column, so a previous-release
  replica calls that upstream without headers until it is replaced] → the window is the rollout. A refused credential
  does not count towards health (UPS-4), and existing rows are not sealed until the first sweep, one interval
  (default 1 h) after start.
- [With `BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL=0`, existing plaintext rows are sealed only when written] → the startup
  warning reports them with `reason=awaiting_reencryption_pass`. The configuration docs say that `0` also disables
  sealing.
- [All keys lost] → static headers become unreadable, like upstream tokens today. The ciphertext is kept, not
  overwritten, so restoring a key recovers the values, and the operator runbook says so.
- [Downgrading past `0017` drops encrypted headers] → this is stated in the migration docstring and the ADR.
  Rolling back the image does not run a downgrade (step 4 below), so the column and its values stay. An operator who
  downgrades the schema anyway re-enters the headers or restores a backup.
- [A third table makes each sweep longer] → servers number in the tens to hundreds. One batch of 100 covers most
  deployments.

## Migration Plan

1. Deploy. Migration `0017` adds a nullable column, and previous-release replicas keep working (DEP-5).
2. From now on, new and updated servers store encrypted headers when a key is configured.
3. One interval after start (default 1 h), the background pass seals the remaining plaintext rows and logs `sealed=<n>`.
   The startup warning disappears on the next restart.
4. Rollback means the previous image. Headers written encrypted meanwhile are invisible to it, so re-enter them, or
   keep the new image until the next release. Logins in flight restart.

## Open Questions

- **Should a gateway with no encryption key refuse to store static headers**, as it already refuses upstream OAuth?
  It is stricter, and it would turn the startup warning into an error. But it breaks existing keyless deployments on
  upgrade, so this design keeps plaintext as the keyless fallback. Tightening it later changes ARC-18 only. The
  re-encryption code built here is needed either way.

## Implementation Notes

Where the implementation refined the plan above, and why:

- **The header ciphertext view returns a typed item.** `header_ciphertexts().page_after` returns `StoredCiphertext`
  (`id`, `ciphertext`), a new frozen model beside `StoredSecrets` in `application/contracts/persistence/`, so nothing
  crosses the layer as a tuple. `SecretReencryption` reads `.ciphertext` from it.
- **Sealing compares the plaintext too.** Besides `static_headers_encrypted IS NULL`, each sealing update also requires
  the plaintext column's stored text to equal what was read. Without it, headers a previous-release replica rewrote in
  plaintext between the read and the update would be overwritten with the sealed old values. The comparison casts the
  `json` column to text, which works on Postgres and sqlite alike.
- **The undecryptable value is remembered, not only the id.** The repository keeps the ciphertext it could not decrypt,
  keyed by server id, and writes exactly that back when the entity is saved with no headers. `session.merge` would
  otherwise copy the row's `None` over the stored value.
- **Every callback refusal clears the cookie.** The callback runs its checks in a private method and renders any
  `HTTPException` through FastAPI's own handler, so a refusal answers in the usual `{"detail"}` shape and still carries
  the expiring `Set-Cookie`.
- **The startup warning runs after the bootstrap document is applied**, not straight after migrations, because the
  document may register servers with static headers.
