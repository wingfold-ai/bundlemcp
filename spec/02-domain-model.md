# 02 — Domain model

**Status:** Accepted · **Origin:** improvement
**Prior art:** `../metamcp/apps/backend/src/db/schema.ts`

## Summary

The entities bundlemcp persists in Postgres, each a SQLModel class
([ARC-3](01-architecture.md)). Simplifications vs. metamcp: no per-user
resource ownership (single workspace), Streamable-HTTP-only servers (no
command/args/env columns), endpoints get a `profile`, upstream OAuth tokens are
per-(server, user) instead of per-server.

## Entities

### McpServer — [10-server-registry.md](10-server-registry.md)
| Field | Notes |
|---|---|
| `id` (uuid), `name` | `name` unique, slug-safe (`^[a-zA-Z0-9_-]+$`) — used as tool prefix |
| `description` | optional |
| `url` | Streamable HTTP endpoint of the upstream |
| `static_headers` (json) | headers always sent upstream (e.g. static bearer) |
| `forward_headers` (json) | client→upstream header forwarding map ([24-identity-forwarding.md](24-identity-forwarding.md)) |
| `auth_mode` | `none` \| `static_headers` \| `upstream_oauth` ([23-upstream-oauth.md](23-upstream-oauth.md)) |
| `health_status`, `last_error` | `ok` \| `error` + message ([10-server-registry.md](10-server-registry.md)) |
| `created_at`, `updated_at` | |

### Tool — [11-tool-discovery.md](11-tool-discovery.md)
Discovered tool cache. `id`, `server_id` FK, `name`, `description`, `title`,
`input_schema` (json), `annotations` (json), `schema_hash`, `last_seen_at`.
Unique `(server_id, name)`.

### Bundle — [12-bundles.md](12-bundles.md)
`id`, `name` (unique, slug-safe), `description` (served as MCP `instructions`),
timestamps.

### BundleServer — [12-bundles.md](12-bundles.md)
M:N bundle↔server. `bundle_id`, `server_id`, `enabled` (bool — server on/off
within the bundle). Unique `(bundle_id, server_id)`.

### BundleTool — [13-tool-management.md](13-tool-management.md)
Per-bundle tool state. `bundle_id`, `tool_id`, `enabled` (bool), overrides:
`override_name`, `override_title`, `override_description`,
`override_annotations` (json). Unique `(bundle_id, tool_id)`. Rows exist only
where state deviates from the default (enabled, no overrides).

### Endpoint — [14-endpoints.md](14-endpoints.md)
| Field | Notes |
|---|---|
| `id`, `name` | `name` globally unique, slug-safe — appears in the public URL |
| `bundle_id` FK | many endpoints may point at one bundle |
| `profile` | `default` \| `claude` \| `chatgpt` ([15-endpoint-profiles.md](15-endpoint-profiles.md)) |
| `auth_modes` (json) | subset of `oauth`, `api_key`, `none` ([14-endpoints.md](14-endpoints.md)) |
| `rate_limit` (json) | optional endpoint + per-client limits ([16-rate-limiting.md](16-rate-limiting.md)) |
| `enabled` (bool) | |

### User — [20-oauth-server.md](20-oauth-server.md) / [21-admin-auth.md](21-admin-auth.md)
Provisioned on first OIDC login (admin UI or OAuth authorize flow). `id`,
`oidc_issuer`, `oidc_sub` (unique together), `email`, `display_name`,
`is_admin`, `created_at`. The `id` is the stable `sub` reported by token
introspection — the key the application layer bills against.

### OAuthClient / OAuthAuthorizationCode / OAuthAccessToken — [20-oauth-server.md](20-oauth-server.md)
bundlemcp's own OAuth 2.1 server state (dynamically registered clients,
10-minute single-use PKCE codes, opaque access tokens with rotating refresh
tokens). Token values stored **hashed**. Codes and tokens carry an
`endpoint_id` **audience** ([OAS-10](20-oauth-server.md)) binding them to the
endpoint they were authorized for.

### OAuthConsent — [20-oauth-server.md](20-oauth-server.md)
Persistent user consent: `user_id`, `client_id`, `endpoint_id`, `granted_at`,
`revoked_at` (nullable). Unique `(user_id, client_id, endpoint_id)`. The
authorize flow skips the consent screen while an unrevoked row exists.

### ApiKey — [22-api-keys.md](22-api-keys.md)
`id`, `name`, `key_hash` (+ `key_prefix` for display), `endpoint_ids` (json
scope, empty = all), `is_active`, `last_used_at`, `created_at`.

### UpstreamOAuthClient / UpstreamOAuthToken — [23-upstream-oauth.md](23-upstream-oauth.md)
Client registration/config per upstream server, and tokens stored per
`(server_id, user_id)` — `user_id` nullable for the shared/service connection.
Unique `(server_id, user_id)`.

### AuditRecord — [50-audit-log.md](50-audit-log.md)
Append-only per-tool-call record: endpoint/bundle/server/tool identifiers and
names, caller (`user_id` or `api_key_id`, auth method), `status`,
`duration_ms`, `error_message`, `session_id`, `created_at`. Indexed for the
UI's filters.

### Config
Key/value runtime settings editable in the UI (timeouts, session lifetime,
log retention …). Env vars (`BUNDLEMCP_*` via pydantic-settings, see
[01-architecture.md](01-architecture.md)) cover deploy-time settings; `Config`
covers runtime-tunable ones.

## Relationships

```
McpServer 1──n Tool
McpServer n──m Bundle          (BundleServer: enabled)
Tool      n──m Bundle          (BundleTool: enabled + overrides)
Bundle    1──n Endpoint        (profile, auth_modes, rate_limit)
User      1──n OAuthAccessToken / UpstreamOAuthToken
Endpoint  1──n AuditRecord (denormalized names retained after deletes)
```

## Requirements

- **DOM-1** All entities above MUST be SQLModel classes; migrations MUST be
  Alembic-managed from the first table.
- **DOM-2** Deleting a server MUST cascade its tools and mapping rows; deleting
  a bundle MUST cascade mappings and endpoints; audit records survive deletes
  (FKs nullable + denormalized name columns).
- **DOM-3** Secret-bearing columns (token values, api keys, client secrets)
  MUST be stored hashed where only equality checks are needed, and MUST NOT
  appear in logs or API responses (upstream OAuth tokens must be recoverable,
  so they are stored encrypted at rest rather than hashed).
- **DOM-4** `name` fields used in URLs or tool prefixes MUST enforce
  `^[a-zA-Z0-9_-]+$` at the Pydantic layer and in a DB constraint.
  **Server names** additionally MUST NOT contain `__` (double underscore), so
  prefixed tool names parse unambiguously ([BND-2](12-bundles.md)).
- **DOM-5** Config-class entities participate in cross-replica cache
  invalidation per [33-state-propagation.md](33-state-propagation.md).

## Out of scope

- Organizations/teams/ownership columns (single workspace — see decision log).

## Open questions

- Encryption mechanism for upstream tokens at rest (app-level Fernet key vs.
  pgcrypto) — decide at implementation. Key provisioning/rotation is specced
  in [DEP-9](71-deployment.md).
