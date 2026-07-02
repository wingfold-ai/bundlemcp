# 22 — API keys

**Status:** Accepted · **Origin:** metamcp carry-over (scoping added, query-param mode dropped)
**Prior art:** `../metamcp/apps/backend/src/middleware/api-key-oauth.middleware.ts`, `api_keys` table

## Summary

API keys authenticate non-OAuth clients (scripts, n8n, CI, server-to-server)
against endpoints, and double as the credential for the management API's
service access ([40-management-api.md](40-management-api.md)).

## Requirements

- **KEY-1** Format `bmcp_sk_<random≥32 bytes urlsafe>`. Shown **once** at
  creation; only `key_hash` (+ display prefix) is stored
  ([DOM-3](02-domain-model.md)).
- **KEY-2** Keys carry a `name`, an optional **endpoint scope** (list of
  endpoint ids; empty = all endpoints), and a **kind**: `endpoint` (can call
  scoped endpoints) or `service` (can also call the management API).
- **KEY-3** Accepted via `Authorization: Bearer bmcp_sk_…` or `X-API-Key`
  header on endpoints with `api_key` in `auth_modes`
  ([EP-3](14-endpoints.md)). **Never via query parameter** (decision log).
- **KEY-4** Deactivation (`is_active=false`) and deletion take effect
  immediately; `last_used_at` is maintained (coarse, e.g. ≥1/min writes) for
  the UI.
- **KEY-5** Key validation is a constant-time hash comparison backed by
  Postgres with a short Redis cache; failures feed the auth rate limiter
  ([RATE-5](16-rate-limiting.md)).

## Out of scope

- Per-key rate limits (use the endpoint's per-client limit — the key IS the
  client identity there).
- Key expiry dates (revocation only, in v1).

## Open questions

- None.
