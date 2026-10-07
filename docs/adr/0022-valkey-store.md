# ADR-0022: Valkey (BSD-3) as the bundled RESP store, not Redis

**Status:** accepted · **Date:** 2026-07-05 · **Relates to:** [ADR-0004](0004-postgres-redis-state-split.md)

## Context

ADR-0004 chose a RESP live-state store alongside Postgres. The compose stack pinned `redis:8-alpine`. Redis's licensing
has since moved off permissive open source: Redis 7.4 (Mar 2024) relicensed from BSD-3-Clause to RSALv2 + SSPLv1
(source-available, not OSI open source); Redis 8.0 (May 2025) re-added AGPLv3, so current Redis is OSI open source again
but under a strong network-copyleft license rather than the permissive BSD it once was. For a self-hostable gateway we
want a permissively licensed, OSI-approved store.

## Decision drivers

- BSD-3 is permissive and OSI-approved; it sidesteps AGPL's network-copyleft entirely, which matters for a store
  operators self-host and may modify.
- Valkey is the most drop-in fork (RESP-compatible, redis-py works unchanged, backed by AWS/Google/Oracle under the
  Linux Foundation), so the switch is a one-line compose image change plus a healthcheck (`valkey-cli`).

## Decision

- **Ship Valkey** (`valkey/valkey:8-alpine`) as the store in `deploy/docker-compose.yml`. Valkey is the Linux-Foundation
  fork of Redis 7.2.4, **BSD-3-Clause**, RESP-wire-compatible.
- **The client stays `redis-py`** (`redis>=…`, MIT-licensed) — it speaks RESP to Valkey unchanged. No application code
  changes: `store/*.py` and the `RateLimiter`/`SignalBus`/`SessionStore` use only core RESP commands
  (`INCR`/`EXPIRE`/`TIME`/pub-sub/`WATCH`) that Valkey fully supports.
- **The connection URL keeps the `redis://` scheme** and the `BUNDLEMCP_REDIS_URL` setting name — `redis://` is the
  standard RESP URL scheme that redis-py uses for any RESP server, so renaming would break existing deployments for no
  functional gain.
- **Terminology:** the store choice is a deployment/product decision, not an architecture change. ADR-0004 and the specs
  describe *a RESP live-state store*; where they say "Redis" they denote that store/protocol. The default product is now
  Valkey; any RESP-compatible server (Valkey, Redis, Redict, Garnet) works.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

- Operators who prefer Redis (any edition) can still point `BUNDLEMCP_REDIS_URL` at it — the gateway is RESP-generic.

### Positive

- The whole default stack is permissively licensed (BSD/MIT/PostgreSQL); no AGPL or source-available component.
- Zero code churn; hermetic tests keep using `fakeredis` (unaffected).

### Trade-offs

- `redis://` scheme and `BUNDLEMCP_REDIS_URL` retain the "redis" word despite Valkey being the server — a cosmetic
  mismatch accepted to avoid a breaking rename; the client library genuinely is redis-py.

