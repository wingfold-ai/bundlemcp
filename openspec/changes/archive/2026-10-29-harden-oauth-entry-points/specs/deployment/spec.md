# Spec Delta

## MODIFIED Requirements

### Requirement: DEP-9 Token encryption key rotation
The upstream-token encryption key ([ARC-18](../architecture/spec.md)) MUST be provisioned via
`BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` (ordered list — first encrypts, all decrypt) enabling rotation: add the new key
first; a stored value under an older key is re-encrypted under the first key when it is next read or written, and a
periodic background job re-encrypts the rest; the gateway reports how many stored values still depend on an older key,
and the old key is dropped once that is zero. Losing all keys invalidates stored upstream connections (documented
consequence, [UPS-29](../upstreams/spec.md) re-connect path). Implemented with `MultiFernet`
([ADR-0017](../../../docs/adr/0017-upstream-oauth-encryption.md)).

The same keys encrypt a server's static header values. These are re-encrypted when the server is written and by the
background job, not when they are read, because they are read on every upstream call. The job also encrypts static
header values still stored in plaintext, and reports how many it sealed. Losing all keys makes stored static header
values unreadable as well; an admin enters them again.

#### Scenario: Old ciphertext still decrypts after rotation
- **GIVEN** a token encrypted under key `old`
- **WHEN** the key list becomes `[new, old]`
- **THEN** the token still decrypts, and new writes are encrypted under `new`

#### Scenario: Reading an old value re-encrypts it
- **GIVEN** the key list `[new, old]` and an upstream token stored under `old`
- **WHEN** a tool call reads that token
- **THEN** the call succeeds and the stored token is afterwards encrypted under `new`

#### Scenario: Background job re-encrypts values nobody reads
- **GIVEN** the key list `[new, old]` and an upstream OAuth client secret stored under `old` that no request reads
- **WHEN** the background re-encryption job runs
- **THEN** the secret is stored under `new`, and the job reports zero values still under an older key

#### Scenario: Only one replica runs the job per interval
- **GIVEN** two replicas sharing one Valkey
- **WHEN** a re-encryption interval elapses
- **THEN** exactly one replica runs the job for that interval

#### Scenario: Re-encryption never overwrites a newer value
- **GIVEN** a token being re-encrypted while a refresh stores new tokens for the same connection
- **WHEN** both writes complete
- **THEN** the stored value decrypts to the refreshed tokens

#### Scenario: Safe to drop the old key
- **GIVEN** the job has reported that no stored value depends on an older key
- **WHEN** the operator restarts the gateway with the key list `[new]`
- **THEN** every stored upstream connection, client secret and static header value still decrypts

#### Scenario: Undecryptable values are reported, not rewritten
- **GIVEN** a stored value that no configured key decrypts
- **WHEN** the job runs
- **THEN** the value is left unchanged and counted separately from the values still under an older key

#### Scenario: Static header values move to the new key
- **GIVEN** the key list `[new, old]` and a server whose static headers are stored under `old`
- **WHEN** the background re-encryption job runs
- **THEN** the headers are stored under `new`, still decrypt to the same values, and the job reports zero values still
  under an older key

#### Scenario: Sealing never overwrites headers an admin just wrote
- **GIVEN** a server whose static headers are stored in plaintext
- **WHEN** an admin writes new headers for it while the job is sealing the old ones
- **THEN** the stored headers decrypt to the admin's new values
