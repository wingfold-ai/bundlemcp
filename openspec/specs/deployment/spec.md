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
([EP-16](../endpoints/spec.md)), the auth-failure lockout, per-IP client-registration limits and
logging ([OPS-8](../operations/spec.md)) derives from this policy
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

#### Scenario: Logs carry the derived client IP
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carrying `X-Forwarded-For: 198.51.100.4` is served
- **THEN** its log lines, the access log line included, carry `client_ip` `198.51.100.4`, not the proxy's address

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
migration step has finished. A replica whose database schema is behind the migration head it ships with SHALL report
`/readyz` not ready ([OPS-10](../operations/spec.md)) until the schema is current.

#### Scenario: Concurrent replicas migrate once
- **WHEN** two replicas of a newer image start at the same time against the same database
- **THEN** one applies the migration while the other waits on the advisory lock and then finds nothing to do

#### Scenario: Replica waits for a one-shot migration job
- **GIVEN** a newer image started without the entrypoint migration step, against a database one migration behind
- **WHEN** an orchestrator polls `/readyz`
- **THEN** it answers 503 until the one-shot migration job has applied the head, and 200 afterwards

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
Zero-downtime deployment MUST be verified by the integration suite against the compose stack: the restart-under-load
test of [SES-12](../sessions/spec.md) runs while two gateway replicas are replaced one at a
time by a rolling `compose up` of a newly built image. Sessions established before the rollout keep working afterwards
without re-initializing, and no request sent during it is answered 404 or 500.

#### Scenario: Session survives a gateway restart
- **GIVEN** a session initialized on the `demo` endpoint
- **WHEN** the gateway container restarts and becomes ready again
- **THEN** `tools/list` with the same `Mcp-Session-Id` returns the tools

#### Scenario: Rolling update under load
- **GIVEN** two gateway replicas behind a round-robin proxy and clients sending requests on open sessions
- **WHEN** a new gateway image is built and the replicas are replaced one at a time, each waiting for the other to be
  ready
- **THEN** every request sent during the rollout succeeds or is answered with a retryable 503, none with 404 or 500
- **AND** every session serves `tools/list` afterwards without re-initializing

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

### Requirement: DEP-10 CI gates
CI (GitHub Actions) MUST run on every pull request: `ruff` (including its security rules), `rumdl`, the import contracts
(`lint-imports`), `pytest`, the generated-OpenAPI drift check, the frontend typecheck (`npm run typecheck`) and the
frontend build, the docs build and documentation consistency checks, LikeC4 model validation
([DOC-10](../documentation/spec.md)), OpenSpec validation, the supply-chain security gate ([DEP-14](spec.md)), Docker
builds of both images, and the integration suite against the compose stack. The Python tests run on every Python version
the packages declare they support. CI SHALL also run every week on `main`, where the secret scan reads the whole
history, and every job SHALL have a time limit, so a job that hangs fails instead of running on. Every job that installs
the Python workspace installs it from `uv.lock` as committed and fails when the lock no longer matches the project
files, instead of re-resolving it. A single `ci-passed` job fails unless every other job succeeded.

#### Scenario: Any failing gate blocks the branch
- **WHEN** any CI job of a pull request fails
- **THEN** the `ci-passed` check fails

#### Scenario: A type error in the web app fails CI
- **GIVEN** a pull request that introduces a TypeScript type error in `apps/web` which `nuxt build` still bundles
- **WHEN** CI runs
- **THEN** the frontend job fails on the typecheck step, and `ci-passed` fails

#### Scenario: A stale lockfile fails CI
- **GIVEN** a pull request that adds a dependency to a `pyproject.toml` without updating `uv.lock`
- **WHEN** CI runs
- **THEN** the first job that installs the workspace fails, saying the lockfile needs to be updated, and `ci-passed`
  fails

#### Scenario: The security gate is required
- **WHEN** the supply-chain security gate of a pull request fails
- **THEN** the `ci-passed` check fails

#### Scenario: Every supported Python version is tested
- **GIVEN** the packages declare `requires-python = ">=3.14"`
- **WHEN** CI runs
- **THEN** the backend tests run on Python 3.14 and on 3.15, and either failing fails `ci-passed`

#### Scenario: A quiet week is still checked
- **GIVEN** no commit landed on `main` for a week
- **WHEN** the weekly run starts
- **THEN** CI runs on `main` as on a push, including the advisory gate and a secret scan of the whole history

#### Scenario: A hung job fails
- **WHEN** a CI job runs past its time limit
- **THEN** the job is cancelled as failed, and `ci-passed` fails

### Requirement: DEP-11 Image publishing
Images (`gateway`, `web`) MUST publish to ghcr.io on every push to `main`, tagged `:latest` (what a continuously
deployed stack pulls) and `:<commit-sha>` (to pin or roll back to an exact build). Releases SHALL publish on tags: a
`v<major>.<minor>.<patch>` tag publishes both images as `:<major>.<minor>.<patch>` and creates a release whose notes
come from the changelog's entry for that version. A merge into `main` that raises the version
([DEP-12](spec.md)) creates that version's tag and publishes its release without anyone pushing a tag; a tag a
maintainer pushes by hand publishes the same way. Every release's notes SHALL state the metering-hook protocol version
([PROT-27](../protocol/spec.md)) and call it out when it changed since the previous release. Every published image SHALL
carry an SBOM and a SLSA provenance record; in a public repository it SHALL also carry a provenance attestation signed
by GitHub that names the workflow and the commit it was built from.

#### Scenario: Push to main publishes both images
- **WHEN** a commit lands on `main`
- **THEN** `bundlemcp-gateway` and `bundlemcp-web` are pushed to ghcr.io as `:latest` and `:<that commit's sha>`

#### Scenario: Merge that raises the version releases it
- **GIVEN** the version on `main` is `1.1.0`
- **WHEN** a pull request that raises it to `1.2.0` is merged
- **THEN** the merge commit is tagged `v1.2.0`, both images are pushed as `:1.2.0`, and a release `v1.2.0` is created
  with the changelog's `1.2.0` entry as its notes

#### Scenario: Merge that keeps the version releases nothing
- **WHEN** a pull request that does not change the version is merged
- **THEN** no tag and no release is created

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

#### Scenario: A published image can be verified
- **GIVEN** the repository is public and an image was published by the publish workflow
- **WHEN** an operator runs `gh attestation verify oci://ghcr.io/<owner>/bundlemcp-gateway:<tag> --owner <owner>`
- **THEN** the verification succeeds and names this repository's workflow and the commit the image was built from

#### Scenario: A published image lists its contents
- **WHEN** an operator inspects a published image's attestations in the registry
- **THEN** it carries an SBOM of the packages in the image and a provenance record of its build

### Requirement: DEP-12 Every pull request carries its release
A pull request into `main` SHALL carry the release its merge makes, so the squash commit is the release commit and
`main` gains no other commit for it.

- **Labels from the title.** The pull request's title MUST be a Conventional Commit (`<type>(<scope>)!: <Subject>`). CI
  derives a `type: <type>` label and a `semver:` label from it, and replaces both whenever the title is edited: `!` is
  `semver: major`; otherwise `feat` is `minor`, `fix`, `perf` and `revert` are `patch`, and every other type is `none`.
  A title that is not a Conventional Commit fails the check and gets no labels. A description that contains a CI-skip
  marker (`[skip ci]` and its variants) fails the check too, because the squash merge takes its message from the
  description and the marker would skip CI and the release on `main`.
- **Next version.** The pull request's version is the version on `main` raised by its `semver:` label. While the major
  version is `0`, a major bump raises the minor and a minor or patch bump raises the patch (`0.1.0` → `0.2.0` and
  `0.1.1`); from `1.0.0` the bumps are literal.
- **Entry and bump on the branch.** For a `semver:` label other than `none`, CI commits to the pull request's branch a
  `CHANGELOG.md` entry `## [<version>] - <date>`, placed above the newest entry on `main`, and raises the project's
  version to it. That commit starts no further CI run. The entry's text is not the title: a language model writes it
  from the pull request's changes and description, as bullets under *Added*, *Changed*, *Fixed* and *Security* that say
  what a user, operator or integrator gets, with a breaking change marked as breaking and a link to the pull request.
  The text is written when the entry is first added and again whenever the author pushes changes, unless someone has
  edited it on the branch since CI last wrote it: an edited text is kept. When the title is edited or `main` moves on,
  CI renumbers the entry and the bump to the next free version and refreshes the date, keeping the text. When the model
  cannot be reached, the entry is the title's subject with the link, and the check says so. A `semver: none` pull
  request gets neither entry nor bump, and any entry or bump CI added earlier is removed.
- **The protocol only when it changes.** An entry names the metering-hook protocol
  ([PROT-27](../protocol/spec.md)) only in a release that changes it. A pull request that raises the protocol version
  MUST be marked breaking (`!`), or its entry check fails; its entry says the protocol changed, with a breaking bullet
  CI adds under *Changed* unless the text already names the protocol. A release whose protocol changed since the
  previous release tag and whose entry does not say so is refused before anything is published. The release notes
  always end with the protocol version, as DEP-11 requires.
- **The merge waits for CI.** `main` MUST only accept a pull request whose `ci-passed` check succeeded on its head.
  CI's own commits on the branch run no CI, so the result CI reached on the commit before them is set on the head as
  that check: pending until that run finishes, then its outcome.
- **Branches CI cannot write.** A pull request from a fork cannot receive the commit; its check fails and says so,
  and a maintainer brings the branch into the repository before merging.

#### Scenario: Feature title becomes a minor release
- **GIVEN** the version on `main` is `1.1.0`
- **WHEN** a pull request titled `feat(bundles): Order members by hand` is opened
- **THEN** it is labelled `type: feat` and `semver: minor`, and its branch gains a commit adding a `## [1.2.0] - <date>`
  entry whose bullets describe the pull request's changes and link to it, and raising the version to `1.2.0`

#### Scenario: Edited entry text is kept
- **GIVEN** a pull request whose entry text a maintainer reworded on the branch
- **WHEN** the author pushes another change
- **THEN** the entry keeps the reworded text, and only its version and date are updated

#### Scenario: Pushed changes rewrite an unedited entry
- **GIVEN** a pull request whose entry text is still the one CI wrote
- **WHEN** the author pushes a change that adds a new setting
- **THEN** the entry's text is written again from the changes and now mentions the setting

#### Scenario: Breaking change below 1.0 raises the minor
- **GIVEN** the version on `main` is `0.1.0`
- **WHEN** a pull request titled `refactor(auth)!: Rename the session cookie` is opened
- **THEN** it is labelled `semver: major`, and its entry and version are `0.2.0`, with the change marked as breaking

#### Scenario: Retitled pull request is re-derived
- **GIVEN** a pull request titled `fix(auth): Reject expired tokens` carrying a `1.1.1` entry
- **WHEN** its title is edited to `feat(auth): Accept refresh tokens`
- **THEN** its labels become `type: feat` and `semver: minor`, and its entry and version become `1.2.0`

#### Scenario: Main moving on renumbers the entry
- **GIVEN** two open pull requests that both carry a `1.2.0` entry
- **WHEN** one of them is merged
- **THEN** the other's entry and version are regenerated as `1.3.0` on its branch, above the merged `1.2.0` entry

#### Scenario: Documentation change is no release
- **WHEN** a pull request titled `docs(repo): Describe the release flow` is opened
- **THEN** it is labelled `type: docs` and `semver: none`, and its branch gains no entry and no version change

#### Scenario: Title that is no Conventional Commit fails
- **WHEN** a pull request titled `Update stuff` is opened
- **THEN** its title check fails naming the expected form, and no labels, entry or bump are added

#### Scenario: Unchanged protocol is not named
- **WHEN** a pull request that leaves the metering-hook protocol version as it is gets its entry
- **THEN** the entry does not mention the protocol

#### Scenario: Protocol change is named as breaking
- **GIVEN** the metering-hook protocol version on `main` is `2`
- **WHEN** a pull request titled `feat(metering)!: Tell the hook more` raises it to `3`
- **THEN** its entry carries a breaking bullet under *Changed* saying the protocol is now `3` and hooks must be updated

#### Scenario: Protocol change without a breaking title fails
- **WHEN** a pull request titled `feat(metering): Tell the hook more` raises the metering-hook protocol version
- **THEN** its entry check fails asking for `!` in the title, and no entry is committed

#### Scenario: Merge waits for CI on the commit before CI's
- **GIVEN** a pull request whose head is CI's entry commit, and CI still running on the author's commit before it
- **WHEN** someone tries to merge it
- **THEN** the merge is refused while the head's `ci-passed` is pending, and allowed once that run succeeds

#### Scenario: Description with a CI-skip marker fails
- **WHEN** a pull request's description quotes a commit subject ending in `[skip ci]`
- **THEN** its check fails asking to reword the description, before the merge could carry the marker to `main`

#### Scenario: The entry commit does not rerun CI
- **WHEN** CI commits the entry and the bump to a pull request's branch
- **THEN** no new CI run starts for that commit

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

### Requirement: DEP-14 Supply-chain security gate
Every pull request and every push to `main` SHALL be checked for: known vulnerabilities in the locked Python and npm
dependencies, development dependencies included (npm at moderate severity or above); secrets in the commits it adds;
lint findings in any Dockerfile; and security findings of static analysis over the Python code. An advisory that
cannot be fixed yet passes only while it is listed, with a reason, in the repository's reviewed allow-list, whose
entries expire within 90 days.

#### Scenario: A locked dependency with a known vulnerability fails
- **GIVEN** a pull request whose `uv.lock` locks a Python package version with a published advisory
- **WHEN** CI runs
- **THEN** the security gate fails and names the package, its version and the advisory

#### Scenario: A moderate npm advisory fails
- **GIVEN** a pull request whose `apps/web` or `docs` lockfile locks a package with an advisory of moderate severity
  or above, in a production or a development dependency
- **WHEN** CI runs
- **THEN** the security gate fails and names the package and the advisory

#### Scenario: A low-severity npm advisory passes
- **GIVEN** the only advisory against an npm lockfile is of low severity
- **WHEN** CI runs
- **THEN** the security gate passes

#### Scenario: An allow-listed advisory passes
- **GIVEN** an advisory with no fixed release, listed in the allow-list with a reason and an expiry date
- **WHEN** CI runs before that date
- **THEN** the security gate passes and reports the advisory as accepted

#### Scenario: An expired allow-list entry fails
- **GIVEN** an allow-list entry whose expiry date has passed
- **WHEN** CI runs
- **THEN** the security gate fails and names the expired entry, whether or not its advisory is still reported

#### Scenario: An allow-list entry too far ahead is refused
- **WHEN** an allow-list entry's expiry is more than 90 days after the day CI runs
- **THEN** the security gate fails and names the entry

#### Scenario: A committed secret fails
- **GIVEN** a pull request with a commit that adds a private key or a live-looking access token
- **WHEN** CI runs
- **THEN** the security gate fails and names the file and the commit, without printing the secret

#### Scenario: A Dockerfile lint finding fails
- **GIVEN** a pull request that adds a Dockerfile instruction the linter reports, at any severity
- **WHEN** CI runs
- **THEN** the security gate fails and names the file, the line and the rule

#### Scenario: An insecure Python pattern fails
- **GIVEN** a pull request that adds library code calling a subprocess through a shell with interpolated input
- **WHEN** CI runs
- **THEN** CI fails on the static-analysis finding, naming the file, the line and the rule

### Requirement: DEP-15 Images are pinned by digest
Every image a Dockerfile builds from or copies from, and every image the compose files run, SHALL be referenced by a
version tag and its content digest, never by a moving tag alone, so a rebuild uses the bytes CI tested. Automated
update pull requests keep tags and digests current. There is no exception: an image a compose file takes from a
variable is pinned in that variable's default too.

#### Scenario: An unpinned image fails the tests
- **GIVEN** a Dockerfile or compose file that names `node:26-alpine` or `example/image:latest` without a digest
- **WHEN** the hermetic test suite runs
- **THEN** it fails and names the file, the line and the image

#### Scenario: A moved tag does not change the build
- **GIVEN** a base image whose tag the publisher has since pointed at new contents
- **WHEN** the gateway image is rebuilt from an unchanged checkout
- **THEN** it is built from the same base image contents as before

#### Scenario: Pinned images still name their runtime version
- **GIVEN** the gateway's base image is referenced as `python:3.15.1-slim-bookworm@sha256:<digest>`
- **WHEN** the runtime-version check ([ARC-2](../architecture/spec.md)) runs
- **THEN** it reads Python `3.15` from that reference

#### Scenario: A variable-chosen image is pinned too
- **GIVEN** a compose service whose image is `${SOME_IMAGE:-example/image:latest}`
- **WHEN** the hermetic test suite runs
- **THEN** it fails on the unpinned default, whatever profile the service belongs to

### Requirement: DEP-16 The development stack runs only what CI can run
Every service the development compose files define SHALL use an image that is built from this repository or pulled
from a public registry, so CI starts the same stack a contributor does. No service, profile or seed file SHALL depend
on a private image or on credentials of an outside service.

#### Scenario: Every compose image is reachable without credentials
- **WHEN** the hermetic test suite reads the development compose files
- **THEN** every service either builds from a directory in this repository or names a public image pinned by digest
  ([DEP-15](spec.md))

#### Scenario: CI starts the whole stack
- **WHEN** CI brings up the development stack for the integration suite
- **THEN** no service is left out because its image cannot be pulled, and no test is skipped because of one

### Requirement: DEP-17 Identity forwarding is verified against a demo upstream
The integration suite SHALL verify, on every pull request, what an upstream learns about its caller. It runs against
an example upstream in the development stack that reports the identity it received, so no maintainer's own server or
outside account is needed. The behaviours covered are header forwarding, the identity header, introspection of
forwarded bearers and static discovery headers ([auth](../auth/spec.md), [upstreams](../upstreams/spec.md)).

#### Scenario: A forwarded bearer is introspected to the caller
- **GIVEN** the demo upstream forwards `authorization` and introspects the bearer it receives
- **WHEN** a signed-in user calls its identity tool through an OAuth endpoint
- **THEN** the tool reports the user's `sub`, and an API-key caller is reported as `api_key:<id>`

#### Scenario: Discovery authenticates with a static header
- **GIVEN** the demo upstream refuses requests without a credential
- **WHEN** an admin forces a tool discovery of it
- **THEN** discovery succeeds through its static header and finds its tools

#### Scenario: The identity header cannot be spoofed
- **WHEN** an API-key caller sends `X-MCP-User: spoofed` to the demo upstream's identity tool
- **THEN** the tool reports `X-MCP-User` as `api_key:<id>`

#### Scenario: Only mapped headers arrive
- **WHEN** a caller sends a mapped tenant header and a header the upstream does not map
- **THEN** the tool reports the tenant value under its upstream name and does not list the unmapped header

#### Scenario: Callers never see each other's identity
- **WHEN** an OAuth caller and an API-key caller call the identity tool alternately on one gateway
- **THEN** every reply reports the identity of the caller that made that call

#### Scenario: The suite runs without a marker
- **WHEN** CI runs the integration suite
- **THEN** the identity-forwarding tests run with every other test, and no marker excludes them

### Requirement: DEP-18 Code scanning
While the repository is public, CodeQL SHALL scan its Python, TypeScript and Vue code and its workflow files on every
pull request, on every push to `main` and weekly, using the extended security queries. Findings are listed under the
repository's code-scanning alerts. While the repository is private, the scan is skipped rather than failed.

#### Scenario: A pull request is scanned
- **GIVEN** the repository is public
- **WHEN** a pull request is opened
- **THEN** CodeQL analyses each of the three languages and reports new alerts on the pull request

#### Scenario: A private repository skips the scan
- **GIVEN** the repository is private
- **WHEN** CI runs
- **THEN** the CodeQL jobs are skipped, and no check fails because of them

### Requirement: DEP-19 Repository scorecard
While the repository is public, OpenSSF Scorecard SHALL rate it weekly, on every push to `main` and when its branch
rules change, publish the result for the badge the README shows, and list its findings under code scanning. While
the repository is private, the rating is skipped.

#### Scenario: The badge shows the current rating
- **GIVEN** the repository is public and Scorecard ran on `main`
- **WHEN** a visitor opens the README
- **THEN** the Scorecard badge shows that run's score and links to its report

## Out of scope

- Kubernetes/Helm (compose-first; the DEP rules are written to transfer).
- HA Postgres/Valkey operation itself (operator's platform concern).

## Notes

Prior art: metamcp `APP_URL`/`EXTRA_TRUSTED_ORIGINS` handling, and the first consumer's Traefik deploy + cookie-domain
bug in its registrar client.
