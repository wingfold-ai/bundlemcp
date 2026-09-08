# 71 — Deployment, upgrades & operations

**Status:** Accepted · **Origin:** new
**Prior art:** metamcp `APP_URL`/`EXTRA_TRUSTED_ORIGINS` handling (`../metamcp/apps/backend/src/auth.ts`), application-layer's Traefik deploy + cookie-domain bug (`../application-layer/packages/registrar/registrar/clients.py`)

## Summary

The operational contract: how a deployment declares its public identity behind
a reverse proxy, how upgrades roll without breaking the "restarts are
non-events" promise, and how state is backed up and keys rotated.

## Requirements

### Public identity & reverse proxy

- **DEP-1** `BUNDLEMCP_PUBLIC_URL` is the single source of the externally
  visible base URL. OAuth issuer, `.well-known` metadata, redirect URIs,
  consent/connect page URLs ([20](20-oauth-server.md)/[23](23-upstream-oauth.md))
  and admin cookie `Domain`/`Secure` attributes ([ADM-1](21-admin-auth.md))
  are all derived from it — never from incoming Host headers.
- **DEP-2** Trusted-proxy config (`BUNDLEMCP_TRUSTED_PROXIES`, CIDR list):
  `X-Forwarded-For/Proto/Host` are honored only when the direct peer is in
  the list; otherwise ignored. Client IP used for rate limiting
  ([RATE-1](16-rate-limiting.md)) and logging derives from this policy — XFF
  from untrusted peers is never believed. The **client-IP half is implemented**
  (`api/http/client_ip.py::client_ip`, [ADR-0018](../docs/adr/0018-rate-limiting.md));
  `X-Forwarded-Proto/Host` handling remains pending.
- **DEP-3** The compose stack and `docs/deploy.md` show the reference
  topology: reverse proxy (TLS) → gateway + web; health checks wired to
  `/healthz`/`/readyz` ([OBS-3](51-observability.md)).

### Upgrades

- **DEP-4** Alembic migrations run as a **dedicated step** (entrypoint mode or
  one-shot job) guarded by a Postgres advisory lock — N replicas starting
  concurrently never double-run; app replicas wait for
  schema-current before serving (`/readyz` false until then).
- **DEP-5** Rolling-deploy rule: migrations MUST be backward-compatible one
  release back (expand/contract pattern — old code runs against the new
  schema during rollout). Destructive contractions ship one release after
  the code stops using them.
- **DEP-6** Redis session records carry a schema `version` field
  ([SES-1](30-session-management.md)); a release MUST read records written by
  the previous release (or treat them as expired gracefully — forcing client
  re-init, never erroring). Incompatible bumps are release-noted.
- **DEP-7** Zero-downtime is verified by the [SES-12](30-session-management.md)
  restart-under-load test run against a rolling `compose up` of a new image.

### State protection

- **DEP-8** Backup/restore runbook in `docs/deploy.md`: Postgres dump/restore
  covers **all** durable state (config, users, tokens, audit); Redis is
  deliberately not backed up (sessions/limits only — loss = clients
  re-initialize). Restore procedure is documented and tested once per
  release cycle.
- **DEP-9** Upstream-token encryption key ([DOM-3](02-domain-model.md)):
  provisioned via `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` (ordered list — first
  encrypts, all decrypt) enabling rotation: add new key first, re-encrypt
  lazily on access + background job, drop the old key after full
  re-encryption. Losing all keys invalidates stored upstream connections
  (documented consequence, [UPO-5](23-upstream-oauth.md) re-connect path).
  **Implemented** via MultiFernet in `crypto.py`
  ([ADR-0017](../docs/adr/0017-upstream-oauth-encryption.md)); the lazy
  re-encryption job is the one remaining follow-up (rotation works today by
  key ordering + `rotate()` on write).

### Release engineering

- **DEP-10** CI (GitHub Actions): every PR runs `ruff`, `pytest`, frontend
  typecheck/build, and LikeC4 model validation ([ADOC-4](62-architecture-documentation.md));
  integration suite runs on main.
- **DEP-11** Images (`gateway`, `web`) publish to ghcr.io on tags; releases
  are semver with a changelog; the metering-hook protocol version
  ([MID-4](31-middleware.md)) is called out in release notes when it changes.

## Out of scope

- Kubernetes/Helm (compose-first; the DEP rules are written to transfer).
- HA Postgres/Redis operation itself (operator's platform concern).

## Open questions

- None.
