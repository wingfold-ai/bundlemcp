# Design: re-encrypting stored secrets after a key rotation

## Context

See `proposal.md` for the motivation and `specs/deployment/spec.md` (DEP-9) for the required behaviour.

Today the token cipher (`infrastructure/crypto/token_cipher.py`) wraps an ordered key list: the first key encrypts,
every key decrypts. The application sees it only through the `SecretCipher` contract (`encrypt`, `decrypt`). Two
durable columns hold its ciphertext:

| Column | Written when | Read when |
|---|---|---|
| upstream OAuth tokens (`tokens_encrypted`) | connect, refresh | every tool call to an OAuth upstream (`UpstreamTokenStorage`, `UpstreamTokenRefresher`) |
| upstream OAuth client secret (`client_secret_encrypted`) | client route, bootstrap, dynamic client registration | token exchange and refresh (`UpstreamTokenStorage._config`) |

A third use, the sealed MRTR `requestState`, is not stored by the gateway: the client holds it and it expires within
minutes, so it needs no re-encryption. Its only consequence is operational — dropping a key invalidates states sealed
under it, so the runbook waits one state lifetime after the last rotation before dropping a key.

Periodic work already has a pattern: `api/jobs/tool_refresher.py` runs a loop on every replica and takes a
self-expiring Valkey lease (`RefreshLock`) so one replica works per interval (ADR-0038).

## Goals / Non-Goals

**Goals:**

- Every stored secret ends up under the primary key without an operator touching rows.
- The operator gets an explicit signal that no stored value depends on an older key.
- Re-encryption never loses a concurrent write and never fails the request that triggered it.

**Non-Goals:**

- Key management itself (generation, storage in a KMS): the operator still supplies the key list.
- Re-encrypting the client-held `requestState`.
- A management API route or UI for the status; the signal is a log event (see Open Questions).

## Decisions

### 1. The cipher contract grows two operations

`SecretCipher` (`application/contracts/secret_cipher.py`) gains `is_current(ciphertext) -> bool` (decrypts under the
primary key alone) and `reencrypt(ciphertext) -> str` (the existing `rotate()`, renamed to say what it does to a value
rather than to the key list). `TokenCipher` implements both; the memory fake used in tests implements them with a
visible key marker. Both stay `@runtime_checkable`.

*Alternative:* a separate `RotatingCipher` contract. Rejected: every implementation of the cipher must support rotation
for DEP-9 to hold, so splitting the contract only adds a second injection point for the same object.

### 2. Conditional writes, never blind overwrites

The upstream token and client repository contracts gain `replace_ciphertext(id, expected, new) -> bool`, an `UPDATE …
WHERE id = :id AND <column> = :expected` in the Postgres adapter and the equivalent in the memory fake. A re-encryption
that loses the race to a refresh or a client update changes nothing, and the next access or sweep retries.

*Alternative:* take the per-connection refresh lock (`REFRESH_LOCK_KEY`) around re-encryption. Rejected: it couples a
storage concern to Valkey and to the refresher's lock layout, and client secrets have no such lock. The compare-and-set
is local to Postgres and covers both columns.

### 3. Lazy re-encryption at the two read sites, best effort

`UpstreamTokenStorage` (`application/upstream_oauth/`) checks `is_current` after loading a token row or client row it is
about to decrypt; when false it re-encrypts and calls `replace_ciphertext` in its own short unit of work, after the
caller has its plaintext. A failure is logged (`token_encryption.reencrypt_failed`, no value) and swallowed: the call in
progress already holds a valid plaintext, and the sweep will retry.

*Alternative:* re-encrypt only on write (today's behaviour). Rejected: it is what left values on the old key forever.

### 4. A leased background sweep

A `SecretReencryption` use case in `application/upstream_oauth/` pages through both tables in id order (batches of
100, one unit of work per batch), re-encrypts every value that is not current, and returns a `ReencryptionSweep` model:
`rewritten`, `remaining_on_old_key`, `undecryptable`. A `SecretReencryptionJob` in `api/jobs/`, shaped like
`ToolRefresher`, runs it every `BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL` seconds (default 3600; `0` disables) under its
own lease key, and logs `token_encryption.swept` with the three counts. `main/composition_root.py` starts it only when a
cipher exists (keys configured). An undecryptable value is never rewritten and never fails the sweep.

*Alternative:* a one-shot CLI command the operator runs after rotating. Rejected as the only mechanism: it needs shell
access to a replica and is easy to forget. It can be added later on top of the same use case.

### Layers

| Piece | Layer |
|---|---|
| `SecretCipher.is_current` / `reencrypt` | `application/contracts/` |
| `TokenCipher` implementation | `infrastructure/crypto/` |
| `replace_ciphertext` on the two repository contracts | `application/contracts/persistence/`, adapters in `infrastructure/postgres/` and `infrastructure/memory/` |
| `SecretReencryption`, `ReencryptionSweep`, lazy path in `UpstreamTokenStorage` | `application/upstream_oauth/` |
| `SecretReencryptionJob` | `api/jobs/` |
| Wiring and the `Settings` field | `main/`, `application/settings/` |

## Risks / Trade-offs

- [A sweep over many rows holds the database] → batches of 100 with one short unit of work each; the sweep yields
  between batches.
- [An operator drops the old key before the sweep reports zero] → the existing documented consequence applies
  (connections re-connect, UPS-29); the runbook tells them to wait for `remaining_on_old_key=0`.
- [A pending `requestState` sealed under a dropped key is refused] → the client restarts the call; the runbook says to
  wait one state lifetime after rotating before dropping the key.
- [Lazy re-encryption adds a write to a read path] → only once per value per rotation, and only after the plaintext is
  in hand.

## Migration Plan

No schema migration: the columns keep their type, only their content changes. Deploy the release, then rotate as the
runbook says: prepend the new key, restart, wait for a `token_encryption.swept` event with `remaining_on_old_key=0`
(and one `requestState` lifetime), remove the old key, restart. Rollback is safe at any point while the old key is still
in the list.

## Open Questions

- Whether to also expose the sweep counts on a management API route or in the Settings page. Deferrable: the log event
  is enough for the runbook, and a route would be an addition to MGMT-1 that can come later.
