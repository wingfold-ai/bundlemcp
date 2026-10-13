## MODIFIED Requirements

### Requirement: DEP-9 Token encryption key rotation
The upstream-token encryption key ([ARC-18](../../../../specs/architecture/spec.md)) MUST be provisioned via
`BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` (ordered list — first encrypts, all decrypt) enabling rotation: add the new key
first; a stored value under an older key is re-encrypted under the first key when it is next read or written, and a
periodic background job re-encrypts the rest; the gateway reports how many stored values still depend on an older key,
and the old key is dropped once that is zero. Losing all keys invalidates stored upstream connections (documented
consequence, [UPS-29](../../../../specs/upstreams/spec.md) re-connect path). Implemented with `MultiFernet`
([ADR-0017](../../../../../docs/adr/0017-upstream-oauth-encryption.md)).

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
- **THEN** every stored upstream connection and client secret still decrypts

#### Scenario: Undecryptable values are reported, not rewritten
- **GIVEN** a stored value that no configured key decrypts
- **WHEN** the job runs
- **THEN** the value is left unchanged and counted separately from the values still under an older key
