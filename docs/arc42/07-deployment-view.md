# 7. Deployment View

LikeC4 deployment view `production` in
[`../likec4/deployment.c4`](../likec4/deployment.c4):

```likec4-view
view: production — "bundlemcp — Deployment (reference topology)"
```

## Reference topology

Operator's reverse proxy (TLS, `X-Forwarded-*`) → N stateless **gateway** replicas + **web** container; **Postgres** and
**Valkey** (the RESP store, BSD-3 — [ADR-0022](../adr/0022-valkey-store.md)) shared by all replicas. No sticky sessions
— the proxy may round-robin freely
([ARC-9](../../openspec/specs/architecture/spec.md)).

| Aspect | Rule | Spec |
|---|---|---|
| Public identity | `BUNDLEMCP_PUBLIC_URL` drives issuer/metadata/cookies; Host headers never trusted | [DEP-1](../../openspec/specs/deployment/spec.md) |
| Proxy trust | `X-Forwarded-For` honored only from `BUNDLEMCP_TRUSTED_PROXIES` CIDRs, read from the right; `X-Forwarded-Proto` and `X-Forwarded-Host` ignored | DEP-2 |
| Migrations | Dedicated step + advisory lock; expand/contract for rolling deploys | DEP-4/5 |
| Session compat | Redis records versioned; new release reads previous release's records | DEP-6 |
| Probes | `/healthz` (live), `/readyz` (PG+Redis+schema current) | [OPS-10](../../openspec/specs/operations/spec.md) |
| Backups | Postgres dump = full durable state; Redis deliberately unbacked; restore rehearsed for every release (`deploy/rehearse_restore.py`) | DEP-8 |
| CI gates | One `ci-passed` check over ruff, rumdl, import contracts, pytest, OpenAPI drift, frontend typecheck and build, docs, LikeC4, OpenSpec, images, integration | DEP-10 |
| Releases | each pull request carries its version (from its title) and `CHANGELOG.md` entry; its merge tags `v<semver>` → restore rehearsal → images `:<version>` → GitHub release from the entry, naming the metering-hook protocol version; `main` publishes `:latest` and `:<sha>` | DEP-11, DEP-12 |
| Dev stack | `deploy/docker-compose.yml`: gateway, web, PG, Valkey, dev OIDC IdP, demo seed | ARC-13, [MGMT-13](../../openspec/specs/management/spec.md) |
