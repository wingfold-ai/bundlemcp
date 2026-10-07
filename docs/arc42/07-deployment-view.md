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
([ARC-9](../../spec/01-architecture.md)).

| Aspect | Rule | Spec |
|---|---|---|
| Public identity | `BUNDLEMCP_PUBLIC_URL` drives issuer/metadata/cookies; Host headers never trusted | [DEP-1](../../spec/71-deployment.md) |
| Proxy trust | `X-Forwarded-*` honored only from `BUNDLEMCP_TRUSTED_PROXIES` CIDRs | DEP-2 |
| Migrations | Dedicated step + advisory lock; expand/contract for rolling deploys | DEP-4/5 |
| Session compat | Redis records versioned; new release reads previous release's records | DEP-6 |
| Probes | `/healthz` (live), `/readyz` (PG+Redis+schema current) | [OBS-3](../../spec/51-observability.md) |
| Backups | Postgres dump = full durable state; Redis deliberately unbacked | DEP-8 |
| Dev stack | `deploy/docker-compose.yml`: gateway, web, PG, Valkey, dev OIDC IdP, demo seed | ARC-13, [BOOT-6](../../spec/41-bootstrap.md) |
