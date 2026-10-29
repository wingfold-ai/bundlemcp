# ADR-0061: Static upstream headers are encrypted in the repository

**Status:** accepted · **Date:** 2026-10-29 · **Amends:** [ADR-0017](0017-upstream-oauth-encryption.md)

## Context

ADR-0017 encrypts upstream OAuth tokens and client secrets at rest under the rotatable
`BUNDLEMCP_TOKEN_ENCRYPTION_KEYS`, and refuses upstream OAuth outright on a gateway without keys. A server's static
headers carry the same kind of secret, a bearer token or an API key the gateway sends upstream, but they were stored
in a plain JSON column, so a database dump or a backup leaked them (audit finding S3, 2026-10-29).

Encryption so far is applied by application services through the `SecretCipher` contract onto `*_encrypted` entity
fields. Static headers are read in plaintext by four consumers that hold no cipher: the upstream client factory, the
inspector, discovery and the configuration export.

## Decision drivers

- With a key configured, no header value may remain at rest in plaintext, including values stored before the upgrade.
- Every consumer of `McpServer.static_headers` stays unchanged.
- A keyless deployment that uses static headers today keeps working after the upgrade.
- Rotation and the leased background pass of [DEP-9](../../openspec/specs/deployment/spec.md) cover the new values.
- A rolling deploy keeps working while previous-release replicas still read the plaintext column.

## Decision

- **The repository adapter encrypts.** `SqlAlchemyServerRepository` takes the optional cipher. With a cipher it writes
  a server's headers as one Fernet token of their canonical JSON (sorted keys) into a new
  `mcp_servers.static_headers_encrypted` column and leaves the plaintext column empty; on read it decrypts, and falls
  back to the plaintext column for a row not yet sealed. The entity keeps plaintext `static_headers`, so no consumer
  changes. This is the first adapter that encrypts a field itself; elsewhere application services still do.
- **Plaintext only without a key.** A keyless gateway reads and writes the plaintext column as before, and logs
  `static_headers.plaintext` at startup with the number of servers concerned, never a name or value.
- **Undecryptable values are kept.** A ciphertext no held key decrypts reads as no headers and is logged by server id.
  Saving that server with no headers in the same unit of work writes the ciphertext back unchanged, so an unrelated
  edit never destroys a value a restored key could decrypt; writing new headers replaces it.
- **Sealing happens at runtime.** Migration `0017` only adds the nullable column. The background re-encryption pass
  first seals rows that still hold plaintext, each with a compare-and-set on the stored text and on the ciphertext
  being absent, then moves header ciphertexts under the primary key like any other stored secret, and reports
  `sealed` beside its other counts. Headers are re-encrypted when the server is written and by the pass, not on read,
  because they are read on every upstream call.
- **Downgrade loses encrypted headers.** Dropping the column below `0017` discards them; the migration docstring says
  so. Rolling back the image runs no downgrade, but a previous release cannot see values stored encrypted.

## Alternatives considered

- **Encrypt in the application services, like client secrets.** Every consumer would need the cipher to decrypt: four
  call sites and a contract dependency in infrastructure code that has none, to reach plaintext they use as is.
- **Encrypt each value inside the JSON column.** Header names would stay readable without a key, but compare-and-set
  needs JSON equality, which the Postgres `json` type lacks, and one column would mix plaintext and ciphertext told
  apart only by a prefix.
- **Encrypt in the Alembic migration with keys read from the environment.** Works only when the keys are in the
  migration's environment, duplicates sealing, and clears plaintext while previous-release replicas still read it.
- **Refuse static headers without a key**, as ADR-0017 does for upstream OAuth. Breaks every keyless deployment that
  has a static-header server today on upgrade. It remains an option; tightening it changes ARC-18 only.

## Consequences

### Positive

- With a key, a database dump or backup carries no static header value once one background pass has run.
- Header values follow the same rotation, reporting and lost-key semantics as upstream tokens.
- No consumer of the entity, no API shape and no export or import changed.

### Trade-offs

- An infrastructure adapter now holds a secret-handling rule, so the repository and its fake differ: the in-memory
  fake keeps plaintext and seals nothing, and encryption is verified against sqlite.
- During a rolling deploy, a server edited on a new replica has an empty plaintext column, and a previous-release
  replica calls that upstream without headers until it is replaced.
- With `BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL=0`, existing plaintext rows are sealed only when they are next written.
- Losing every key makes stored header values unreadable; an admin enters them again.
