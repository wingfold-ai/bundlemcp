# Proposal: re-encrypt stored secrets after a key rotation

## Why

`BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` supports rotation by ordering — the first key encrypts, all keys decrypt — but a
stored value moves to the new key only when it happens to be written again. Upstream tokens are rewritten on refresh,
but a client secret or a token that is never refreshed stays under the old key indefinitely, so an operator can never
know when it is safe to drop the old key. The original DEP-9 asked for lazy re-encryption on access plus a background
job; the cipher's `rotate()` exists for exactly this and is called by nothing outside tests.

## What Changes

- A stored secret (upstream OAuth tokens, upstream OAuth client secrets) that is read while encrypted under a
  non-primary key is re-encrypted under the primary key on that access.
- A background job, run by one replica per interval, re-encrypts every remaining stored secret under the primary key
  and reports how many values still depend on another key.
- The operator can tell when that count reaches zero, which is when the old key may be dropped; the rotation runbook in
  `docs/self-hosting/operations.md` says so.
- A new setting controls the job's interval (`0` disables it).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: DEP-9 (re-encryption on access plus a background job; the old key is dropped once nothing depends on
  it, which the gateway reports).

## Impact

- **Code:** the secret-cipher contract (`application/contracts/`) gains re-encryption and a primary-key check, fulfilled
  by the token cipher in `infrastructure/crypto/`; a re-encryption use case in `application/upstream_oauth/`; the
  upstream token and client repositories gain a conditional ciphertext update; a periodic job in `api/jobs/` wired in
  `main/composition_root.py`; a new `Settings` field.
- **Configuration:** one new `BUNDLEMCP_*` setting, documented in `docs/self-hosting/configuration.md`.
- **Docs:** `docs/self-hosting/operations.md` (*Token encryption keys*), and arc42 §8 where encryption at rest is
  described. ADR-0017 says `rotate()` re-encrypts lazily on write, which was never true; ADRs are append-only, so it is
  left as written and this change completes the rotation story it records. No new ADR: the job follows the leased
  periodic-job pattern of ADR-0038.
- **Depends on** nothing.
