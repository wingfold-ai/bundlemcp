## ADDED Requirements

### Requirement: DEP-13 Development stack exposes no published credential
The development stack started through `deploy/stack.sh` SHALL hold no credential whose value is published in the
repository: it generates the initial service key, the token encryption key and the identity provider's admin password
into `deploy/.env` when missing or equal to a published default, and refuses a public tunnel while the running gateway
accepts a published service key. Its host ports listen on loopback only.

#### Scenario: A fresh checkout gets generated secrets
- **GIVEN** no `deploy/.env` exists
- **WHEN** a developer runs `deploy/stack.sh up`
- **THEN** `deploy/.env` holds a service key, a token encryption key and an identity-provider admin password that are
  not the values in `.env.example` or `docker-compose.yml`, and the generated service key is printed once

#### Scenario: A published default is replaced
- **GIVEN** `deploy/.env` holds the service key published in `.env.example`
- **WHEN** a developer runs `deploy/stack.sh up`
- **THEN** the key in `deploy/.env` is replaced by a generated one before the gateway starts

#### Scenario: An existing encryption key is rotated, not dropped
- **GIVEN** `deploy/.env` holds only the published token encryption key, and upstream tokens are stored
- **WHEN** a developer runs `deploy/stack.sh up`
- **THEN** a generated key is placed first and the published key is kept after it, so the stored tokens are still
  readable and are re-encrypted with the new key

#### Scenario: No tunnel while the published key still works
- **GIVEN** the gateway's data volume holds the service key published in `.env.example`
- **WHEN** a developer runs `deploy/stack.sh up` with `TUNNEL=quick`
- **THEN** the tunnel is stopped, the command exits non-zero, and the message says to revoke that key in the admin UI
  or rebuild the stack

#### Scenario: Host ports listen on loopback
- **WHEN** the development stack is up
- **THEN** every port it publishes on the host is bound to `127.0.0.1`, and none is reachable through another
  interface of the host

#### Scenario: Plain compose keeps working
- **WHEN** an operator runs `docker compose -f deploy/docker-compose.yml up` without `deploy/.env`
- **THEN** the stack starts with its built-in development values, listens on loopback only, and opens no tunnel
