# Tasks

## 1. Login bound to the browser (AUTH-15)

- [x] 1.1 Move `BROWSER_STATE_TTL` from `main/composition_root.py` into `api/oauth/browser_state/` and import it from
  there in the composition root. Add `api/oauth/login_binding_cookie.py` with `login_binding_cookie_name(secure)`
  (`__Host-bmcp_login` or `bmcp_login`) and `login_binding_cookie_kwargs(secure)` (`HttpOnly`, `SameSite=Lax`,
  `Path=/`, no `Domain`, `max_age=BROWSER_STATE_TTL`). Verify with `uv run lint-imports` and with a unit test,
  `test_auth15_binding_cookie_attributes_follow_public_url`.
- [x] 1.2 Add the required, described `browser_binding_hash` field to `OidcLoginState`.
  - `/login` generates the binding, stores its hash and sets the cookie on the redirect.
  - `/login/callback` refuses a missing cookie before touching Valkey, takes the state, compares the hashes in
    constant time, and expires the cookie on every response.
  - Verify in `tests/api/test_oidc.py`:
    - `test_auth15_callback_from_another_browser_is_refused` (no cookie: 400, no session cookie, the fake provider's
      exchange is never called);
    - `test_auth15_mismatched_binding_is_refused` (two logins, the first callback: 400);
    - `test_auth15_https_binding_cookie_uses_host_prefix`;
    - `test_auth15_callback_expires_binding_cookie` (on success and on refusal);
    - every existing `test_oidc.py` and `test_oauth.py` login test, which still pass through the test client's
      cookie jar.
- [x] 1.3 Document the binding cookie and the "start the login again" case in `docs/integrate/http-surface.md`
  ("Browser login and upstream connect") and in `docs/self-hosting/troubleshooting.md`. Verify with
  `python3 tools/check_docs_links.py` and `uv run rumdl check docs`.

## 2. Bounded `/oauth/*` bodies and registration metadata (SEC-7, AUTH-2)

- [x] 2.1 Extend `RequestBodyLimit`:
  - Add `OAUTH_PATH` and a fixed `OAUTH_BODY_LIMIT = 64 * 1024`, chosen per path, so the runtime limit is not read for
    OAuth paths.
  - Give `too_large` the OAuth error shape (`invalid_request` plus `error_description`) for those paths.
  - Update the module and class docstrings.
  - Verify in `tests/api/test_request_body_limit.py`:
    - `test_sec7_oauth_register_declared_length_over_limit` (413, OAuth shape, no client stored);
    - `test_sec7_oauth_chunked_body_over_limit`;
    - `test_sec7_oauth_limit_ignores_runtime_limit` (runtime limit raised, `/oauth/token` with 100 KiB still 413);
    - the existing SEC-7 tests, unchanged.
- [x] 2.2 Add the bounds to `ClientRegistrationRequest`:
  - `redirect_uris`: at most 10 items, each at most 2048 characters;
  - `client_name` at most 200 characters, and `scope` at most 1000;
  - `grant_types` and `response_types`: at most 10 items each.

  Write each bound into the field description in words. Verify in `tests/api/test_oauth.py` with
  `test_auth2_oversized_metadata_refused` (parametrised over each field, 400 `invalid_client_metadata` naming the
  field, no client stored) and `test_auth2_metadata_at_bounds_accepted`.
- [x] 2.3 Document the 64 KiB `/oauth/` limit and the registration bounds:
  - in `docs/integrate/http-surface.md`, in the limits table and the `/oauth/register` row;
  - in `docs/integrate/errors.md`, the 413 shape on `/oauth/`.

  Then run `cd apps/web && npm run openapi` and confirm that `apps/web/openapi.json` and `apps/web/types/api.d.ts` are
  unchanged, or commit the regenerated files.

## 3. Encrypted static headers in storage (ARC-18, SEC-10)

- [x] 3.1 Add the nullable `static_headers_encrypted` `Text` column to `McpServerRow`, with a description, and add
  Alembic migration `0017_encrypted_static_headers` (add column; downgrade drops it, and the docstring states that
  encrypted headers are lost). Verify with `tests/infrastructure/test_encrypted_static_headers_migration.py`:
  `test_arc18_migration_adds_column_and_keeps_plaintext` (upgrade from `0016` keeps existing plaintext rows readable).
  Verify also with the readiness probe's shipped-migration test.
- [x] 3.2 Give `SqlAlchemyServerRepository` an optional `SecretCipher`, and override `_to_row` and `_to_entity` to
  encrypt, decrypt and fall back to plaintext as design.md describes. This includes keeping an undecryptable
  ciphertext through an empty write within the unit of work. Thread the cipher through `SqlAlchemyUnitOfWork` and
  `SqlAlchemyUnitOfWorkFactory`, and build it before the factory in `CompositionRoot`. Verify in
  `tests/infrastructure/test_server_repository_encryption.py`:
  - `test_arc18_static_headers_stored_encrypted` (the raw row holds no plaintext, and the entity reads back equal);
  - `test_arc18_without_cipher_stores_plaintext`;
  - `test_arc18_plaintext_row_read_with_cipher`;
  - `test_arc18_undecryptable_headers_kept_on_unrelated_write`;
  - `test_sec10_static_header_values_are_ciphertext_in_database`.
- [x] 3.3 Add the end-to-end check: a server registered through the management API with a key configured is called
  with its header upstream. Verify with `test_arc18_encrypted_header_reaches_upstream` in `tests/api/`, against a
  fake upstream recording request headers. Also run the existing export and import tests (MGMT-18) unchanged.

## 4. Sealing and rotation of static headers (DEP-9, ARC-18)

- [x] 4.1 Move `StoredSecrets` to `application/contracts/persistence/stored_secrets.py`. Add three methods to the
  `ServerRepository` contract: `header_ciphertexts()`, `seal_plaintext_headers(limit)` and `count_plaintext_headers()`.
  Implement them in the SQLAlchemy adapter, with compare-and-set guards, and in `InMemoryServerRepository`. Verify
  with `uv run lint-imports` (application imports no adapter, and contracts import no use case) and with
  `test_dep9_seal_skips_row_written_meanwhile` in `tests/infrastructure/`.
- [x] 4.2 Extend `SecretReencryption.sweep` and `ReencryptionSweep`:
  - Sealing runs first, in batches, then the server-header table is swept as a third pass.
  - `ReencryptionSweep` gains a described `sealed` counter.
  - `SecretReencryptionJob` logs it on `token_encryption.swept`, and its docstring names static headers.

  Verify with:
  - `test_dep9_static_headers_move_to_new_key` and `test_dep9_sweep_seals_plaintext_headers` (sqlite, key list
    `[new, old]`);
  - `test_dep9_undecryptable_static_headers_counted`;
  - the existing `test_key_reencryption_on_fakes.py` and `test_secret_reencryption_job.py`.
- [x] 4.3 Log `static_headers.plaintext` at startup when `count_plaintext_headers()` is non-zero, with `servers` and
  `reason`. Verify with `test_arc18_keyless_startup_warns_with_count_only` (captured logs; the redaction helper finds no
  header name or value) and `test_arc18_no_warning_when_nothing_plaintext`.

## 5. Decision record and operator docs

- [x] 5.1 Write ADR-0061 "Static upstream headers are encrypted in the repository" (amends ADR-0017). Its decision is
  that the repository adapter encrypts, plaintext is used only without a key, and sealing happens at runtime; its
  alternatives are the ones in design.md. List it in `docs/adr/README.md` and in arc42 §9, mark ADR-0017 as amended
  by 0061, and update arc42 §8 ("upstream tokens, client secrets and static header values encrypted with rotatable
  keys"). Verify with `python3 tools/check_adr_graph.py` and `python3 tools/check_docs_links.py`.
- [x] 5.2 Update the operator docs:
  - In `docs/self-hosting/configuration.md`, the `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` row (it also encrypts static
    header values, which stay plaintext without it) and the `BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL` row (the pass also
    seals plaintext headers, and `0` disables that).
  - In `docs/self-hosting/operations.md`, rotation: static headers, the `sealed` count, and the startup warning.
  - The `Settings` field descriptions of both settings, to match.

  Verify with `python3 tools/check_docs_settings.py` and `python3 tools/check_docs_symbols.py`.

## 6. Gates

- [x] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` (after
  deleting `.import_linter_cache`, since `StoredSecrets` moved), `python3 tools/check_docs_links.py`,
  `python3 tools/check_docs_symbols.py`, `python3 tools/check_docs_settings.py`, `python3 tools/check_adr_graph.py`,
  `python3 tools/check_compose_ports.py`, `python3 tools/check_spec_ids.py`, `cd apps/web && npm run openapi` (no
  drift) and `openspec validate --all --strict`. All must pass.
