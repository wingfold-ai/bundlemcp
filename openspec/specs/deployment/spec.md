# deployment Specification

## Purpose

Running bundlemcp in production and upgrading it safely. The public URL as the single source of the gateway's identity
behind a reverse proxy, trusted proxies and the client IP, the reference topology and health checks, migrations as a
guarded step that stays backward compatible one release back, versioned session records so rolling upgrades work, backup
and restore, rotation of the token encryption keys, and the CI gates and image publishing that deliver it.

Configuration settings themselves are documented per feature; this slice is the operational contract.

## Requirements

### Requirement: DEP-1 Public URL is the single source of identity
`BUNDLEMCP_PUBLIC_URL` MUST be the single source of the externally visible base URL. OAuth issuer, `.well-known`
metadata, redirect URIs, consent/connect page URLs ([auth](../auth/spec.md)/
[upstreams](../upstreams/spec.md)) and the admin session cookie's `Secure` attribute
([AUTH-15](../auth/spec.md)) are all derived from it — never from incoming Host headers. The cookie is host-only
(no `Domain` attribute), `HttpOnly` and `SameSite=Lax`.

#### Scenario: Login return URL behind a proxy
- **GIVEN** `BUNDLEMCP_PUBLIC_URL=https://gw.example.com` and a request arriving with `Host: internal:8000`
- **WHEN** an unauthenticated browser hits `/oauth/authorize` and is sent to login
- **THEN** the login's return URL is built under `https://gw.example.com`, not from the `Host` header

#### Scenario: Secure cookie on an https public URL
- **WHEN** `BUNDLEMCP_PUBLIC_URL` is `https://…` and an admin signs in
- **THEN** the session cookie is set with `Secure`

### Requirement: DEP-2 Trusted proxies decide the client IP
Trusted-proxy config (`BUNDLEMCP_TRUSTED_PROXIES`, CIDR list): `X-Forwarded-For` MUST be honored only when the direct
peer is in the list; otherwise it is ignored and the socket peer is the client IP. The client IP used for rate limiting
([EP-16](../endpoints/spec.md)), the auth-failure lockout and per-IP client-registration limits derives from this policy
— XFF from untrusted peers is never believed ([ADR-0018](../../../docs/adr/0018-rate-limiting.md)). When the peer is
trusted, the XFF list is read from the right and the first entry that is not itself a trusted proxy is the client IP;
the entries to its left were written by the client and are never used. When every entry is a trusted proxy, the leftmost
entry is taken. `X-Forwarded-Proto` and `X-Forwarded-Host` are ignored from every peer, trusted or not: every externally
visible URL derives from the public URL ([DEP-1](../deployment/spec.md)), so the request's own scheme and host are never
used to build one. No component other than this policy interprets forwarding headers.

#### Scenario: Untrusted peer cannot spoof its IP
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES` is empty
- **WHEN** a request from `203.0.113.7` carries `X-Forwarded-For: 10.0.0.1`
- **THEN** the client IP is `203.0.113.7`

#### Scenario: Trusted proxy forwards the client IP
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carries `X-Forwarded-For: 198.51.100.4, 172.18.0.1`
- **THEN** the client IP is `198.51.100.4`

#### Scenario: Client-written entries are ignored
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carries `X-Forwarded-For: 1.2.3.4, 198.51.100.4` because the client sent
  `X-Forwarded-For: 1.2.3.4` and the proxy appended the address it saw
- **THEN** the client IP is `198.51.100.4`, and rate limits and lockouts count against it

#### Scenario: Forwarded scheme and host are ignored
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carries `X-Forwarded-Proto: http` and `X-Forwarded-Host: evil.example`
- **THEN** the OAuth metadata and every redirect the gateway issues still name the public URL's scheme and host

### Requirement: DEP-3 Reference topology and health checks
The compose stack and `docs/self-hosting/deploy.md` MUST show the reference topology: reverse proxy (TLS) → gateway +
web (in compose, the `tunnel`/`ngrok` profiles' Caddy proxy in `deploy/proxy/Caddyfile`; in the docs, the LikeC4
`production` view); health checks wired to `/readyz` ([operations](../operations/spec.md)) — the gateway image's
`HEALTHCHECK` and the compose `healthcheck` poll it, and `/healthz` reports liveness.

#### Scenario: Compose waits for a ready gateway
- **WHEN** the stack is started with `docker compose -f deploy/docker-compose.yml up --wait`
- **THEN** the command returns only after the gateway's `/readyz` health check passes

### Requirement: DEP-4 Migrations as a guarded dedicated step
Alembic migrations MUST run as a **dedicated step** (the gateway image's entrypoint runs `alembic upgrade head` before
starting the server, or an operator runs it as a one-shot pre-deploy job) guarded by a Postgres advisory lock — N
replicas starting concurrently never double-run. A replica does not bind its port, and so serves nothing, until the
migration step has finished.

#### Scenario: Concurrent replicas migrate once
- **WHEN** two replicas of a newer image start at the same time against the same database
- **THEN** one applies the migration while the other waits on the advisory lock and then finds nothing to do

### Requirement: DEP-5 Backward-compatible migrations
Rolling-deploy rule: migrations MUST be backward-compatible one release back (expand/contract pattern — old code runs
against the new schema during rollout). Destructive contractions ship one release after the code stops using them.

#### Scenario: Old replica during rollout
- **GIVEN** a rolling deploy in which the new release's migration has run
- **WHEN** a replica of the previous release still serves requests
- **THEN** its queries succeed against the new schema

### Requirement: DEP-6 Versioned session records
Valkey session records MUST carry a schema `version` field ([SES-1](../sessions/spec.md)); a release MUST
read records written by the previous release (or treat them as expired gracefully — forcing client re-init, never
erroring). Incompatible bumps are release-noted.

#### Scenario: Incompatible record reads as expired
- **GIVEN** a stored session record whose `version` differs from this build's
- **WHEN** the session is looked up
- **THEN** it reads as absent, so the client gets the re-initialize signal and no error

### Requirement: DEP-7 Restart survival is tested
The integration suite MUST verify against the compose stack that a session established before a gateway restart keeps
working afterwards ([SES-12](../sessions/spec.md)): it initializes a session, runs
`docker compose restart gateway`, and calls `tools/list` with the same session id without re-initializing.

#### Scenario: Session survives a gateway restart
- **GIVEN** a session initialized on the `demo` endpoint
- **WHEN** the gateway container restarts and becomes ready again
- **THEN** `tools/list` with the same `Mcp-Session-Id` returns the tools

### Requirement: DEP-8 Backup and restore runbook
`docs/self-hosting/deploy.md` MUST carry the backup/restore runbook: Postgres dump/restore covers **all** durable state
(config, users, tokens, audit); Valkey is deliberately not backed up (sessions/limits only — loss = clients
re-initialize). The restore procedure is documented as a rehearsal (scratch database, load the dump, start a gateway
with the same encryption keys, check `/readyz`, make one real tool call), and the rehearsal SHALL be run once per
release cycle: an automated workflow performs it against the compose stack for every release tag, and can be started
on demand.

#### Scenario: Operator finds the restore rehearsal
- **WHEN** an operator reads the *Backups* section of `docs/self-hosting/deploy.md`
- **THEN** it gives the `pg_dump` command, states that Valkey is not backed up and why, and lists the restore rehearsal
  steps

#### Scenario: Release tag rehearses the restore
- **WHEN** a release tag is pushed
- **THEN** a workflow dumps a seeded compose stack's database, restores it into a scratch database, starts a gateway on
  it with the same encryption keys, waits for `/readyz` and makes one successful tool call

#### Scenario: Failed rehearsal is visible
- **GIVEN** a restore rehearsal whose tool call fails
- **WHEN** the workflow finishes
- **THEN** it reports failure, and the release is not published

### Requirement: DEP-9 Token encryption key rotation
The upstream-token encryption key ([ARC-18](../architecture/spec.md)) MUST be provisioned via
`BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` (ordered list — first encrypts, all decrypt) enabling rotation: add the new key
first; a stored value under an older key is re-encrypted under the first key when it is next read or written, and a
periodic background job re-encrypts the rest; the gateway reports how many stored values still depend on an older key,
and the old key is dropped once that is zero. Losing all keys invalidates stored upstream connections (documented
consequence, [UPS-29](../upstreams/spec.md) re-connect path). Implemented with `MultiFernet`
([ADR-0017](../../../docs/adr/0017-upstream-oauth-encryption.md)).

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

### Requirement: DEP-10 CI gates
CI (GitHub Actions) MUST run on every pull request: `ruff`, `rumdl`, the import contracts (`lint-imports`), `pytest`,
the generated-OpenAPI drift check, the frontend typecheck (`npm run typecheck`) and the frontend build, the docs build
and documentation consistency checks, LikeC4 model validation
([DOC-10](../documentation/spec.md)), OpenSpec validation, Docker builds of both images, and
the integration suite against the compose stack. A single `ci-passed` job fails unless every other job succeeded.

#### Scenario: Any failing gate blocks the branch
- **WHEN** any CI job of a pull request fails
- **THEN** the `ci-passed` check fails

#### Scenario: A type error in the web app fails CI
- **GIVEN** a pull request that introduces a TypeScript type error in `apps/web` which `nuxt build` still bundles
- **WHEN** CI runs
- **THEN** the frontend job fails on the typecheck step, and `ci-passed` fails

### Requirement: DEP-11 Image publishing
Images (`gateway`, `web`) MUST publish to ghcr.io on every push to `main`, tagged `:latest` (what a continuously
deployed stack pulls) and `:<commit-sha>` (to pin or roll back to an exact build). Releases SHALL publish on tags: a
`v<major>.<minor>.<patch>` tag publishes both images as `:<major>.<minor>.<patch>` and creates a release whose notes
come from the changelog's entry for that version. Every release's notes SHALL state the metering-hook protocol version
([PROT-27](../protocol/spec.md)) and call it out when it changed since the previous release.

#### Scenario: Push to main publishes both images
- **WHEN** a commit lands on `main`
- **THEN** `bundlemcp-gateway` and `bundlemcp-web` are pushed to ghcr.io as `:latest` and `:<that commit's sha>`

#### Scenario: Release tag publishes a versioned release
- **WHEN** the tag `v1.2.0` is pushed
- **THEN** both images are pushed as `:1.2.0`, and a release `v1.2.0` is created with the changelog's `1.2.0` entry as
  its notes

#### Scenario: Metering protocol change is called out
- **GIVEN** the metering-hook protocol version differs from the one the previous release shipped
- **WHEN** the release is created
- **THEN** its notes name the new protocol version and say that it changed

#### Scenario: Tag without a changelog entry is refused
- **WHEN** a release tag is pushed for a version the changelog has no entry for
- **THEN** the release workflow fails before publishing anything

## Out of scope

- Kubernetes/Helm (compose-first; the DEP rules are written to transfer).
- HA Postgres/Valkey operation itself (operator's platform concern).

## Notes

Prior art: metamcp `APP_URL`/`EXTRA_TRUSTED_ORIGINS` handling, and the first consumer's Traefik deploy + cookie-domain
bug in its registrar client.
