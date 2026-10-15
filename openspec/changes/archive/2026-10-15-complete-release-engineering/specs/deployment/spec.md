## MODIFIED Requirements

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
