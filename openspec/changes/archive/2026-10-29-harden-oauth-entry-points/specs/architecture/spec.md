# Spec Delta

## MODIFIED Requirements

### Requirement: ARC-18 Secret-bearing columns
Secret-bearing columns (token values, api keys, client secrets) MUST be stored hashed where only equality checks are
needed, and MUST NOT appear in logs or API responses (upstream OAuth tokens and client secrets must be recoverable, so
they are stored encrypted at rest rather than hashed).

A server's static header values are recoverable secrets too, because the gateway sends them upstream. With an
encryption key configured ([DEP-9](../deployment/spec.md)) they MUST be stored encrypted, under the same keys as
upstream tokens; values stored before a key was configured are encrypted by the background re-encryption pass. Only a
gateway with no encryption key stores them in plaintext, and it logs a warning at startup naming how many servers hold
plaintext header values (never the names or values themselves). A stored value no configured key decrypts is treated
as absent when the server is called, and is kept until an admin writes new headers for that server.

#### Scenario: Gateway-issued secrets are stored as hashes
- **WHEN** an API key, an OAuth client secret, an authorization code or an access/refresh token is issued
- **THEN** only its hash is persisted (`key_hash`, `client_secret_hash`, `code_hash`, `access_token_hash`,
  `refresh_token_hash`)

#### Scenario: Upstream tokens are encrypted, not hashed
- **WHEN** an upstream OAuth token set is stored
- **THEN** it is persisted encrypted (`tokens_encrypted`) and can be decrypted for the upstream call

#### Scenario: Static header values are encrypted, not hashed
- **GIVEN** a gateway with an encryption key
- **WHEN** a server is registered with static header `Authorization: Bearer s3cret`
- **THEN** the header is persisted encrypted (`static_headers_encrypted`) and the plaintext column holds nothing
- **AND** a tool call to that server still sends `Authorization: Bearer s3cret` upstream

#### Scenario: Headers stored before the upgrade are encrypted by the background pass
- **GIVEN** a server whose static headers were stored in plaintext, and a gateway that now has an encryption key
- **WHEN** the background re-encryption pass runs
- **THEN** the headers are stored encrypted, the plaintext column holds nothing, and the pass reports them as sealed

#### Scenario: A keyless gateway keeps working and says so
- **GIVEN** a gateway with no encryption key and two servers with static headers
- **WHEN** the gateway starts
- **THEN** both servers are still called with their headers
- **AND** a warning is logged once, naming the count of servers with plaintext header values and no header name or
  value

#### Scenario: Undecryptable headers are kept, not overwritten
- **GIVEN** a server whose stored headers no configured key decrypts
- **WHEN** an admin changes only the server's description
- **THEN** the stored ciphertext is unchanged, and the server is read back with no static header names
