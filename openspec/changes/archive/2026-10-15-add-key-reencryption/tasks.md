# Tasks

## 1. Cipher contract (DEP-9)

- [x] 1.1 Add `is_current` and `reencrypt` to `SecretCipher` and implement them in `TokenCipher` (replacing `rotate`)
  and in the memory fake; verify unit tests citing DEP-9 that a value under the old key is not current, re-encrypts to a
  current value that decrypts to the same plaintext, and that an undecryptable value raises `DecryptionError`

## 2. Conditional ciphertext writes

- [x] 2.1 Add `replace_ciphertext(id, expected, new)` to the upstream token and upstream client repository contracts,
  with the Postgres adapter's conditional `UPDATE` and the memory fake; verify sqlite and fake tests citing DEP-9 that
  a stale `expected` changes nothing and returns false

## 3. Lazy re-encryption on access

- [x] 3.1 In `UpstreamTokenStorage`, re-encrypt a token row or client secret that is not current after decrypting it,
  in its own unit of work, logging `token_encryption.reencrypt_failed` without any value on failure; verify tests citing
  DEP-9 that a read under `[new, old]` leaves the row under `new`, that a failing write does not fail the read, and
  that a concurrent refresh's value survives

## 4. Background sweep

- [x] 4.1 Add `SecretReencryption` and its `ReencryptionSweep` result model (every field described) in
  `application/upstream_oauth/`, paging both tables in batches; verify tests citing DEP-9 for rewritten,
  remaining-on-old-key and undecryptable counts on the memory fakes
- [x] 4.2 Add `SecretReencryptionJob` in `api/jobs/` on the `RefreshLock` lease pattern and the
  `token_reencryption_interval` setting (`BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL`, default 3600, `ge=0`, described);
  wire it in `main/composition_root.py` only when a cipher exists; verify tests citing DEP-9 that a held lease skips the
  tick, `0` starts no job, and the `token_encryption.swept` event carries the counts
- [x] 4.3 Add an integration test against the compose stack (two keys, a seeded old-key row, sweep, restart with only
  the new key, tool call succeeds); verify it passes in the integration job

## 5. Documentation

- [x] 5.1 Rewrite *Token encryption keys* in `docs/self-hosting/operations.md` as the rotation runbook from
  `design.md` (prepend, wait for `remaining_on_old_key=0` and one `requestState` lifetime, drop, restart), document the
  new setting in `docs/self-hosting/configuration.md`, and update arc42 §8 on encryption at rest; verify
  `python3 tools/check_docs_settings.py` and `check_docs_symbols.py` pass

## 6. Gates

- [x] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass
- [x] 6.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [x] 6.3 Run `openspec validate --all --strict` and verify it passes (no DTO or route changes, so no
  `npm run openapi`)
