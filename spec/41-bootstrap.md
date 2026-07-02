# 41 — Bootstrap provisioning

**Status:** Accepted · **Origin:** metamcp carry-over (fork feature)
**Prior art:** `../metamcp/apps/backend/src/lib/bootstrap.service.ts` (`BOOTSTRAP_*` env JSON)

## Summary

Declarative, idempotent provisioning of servers, bundles, endpoints, and API
keys at gateway startup — so ultra-mcp, CI, or any operator can stand up a
fully configured gateway from config alone, no UI clicks.

## Requirements

- **BOOT-1** Source: `BUNDLEMCP_BOOTSTRAP_FILE` (path to a YAML/JSON file,
  compose-friendly) and/or `BUNDLEMCP_BOOTSTRAP` (inline JSON). The document
  is a Pydantic-validated model mirroring the export format
  ([42-export-import.md](42-export-import.md)) plus API keys.
- **BOOT-2** Applied on startup as **upserts by natural key** (server/bundle/
  endpoint names) — semantically the same operations as the management API
  ([API-4](40-management-api.md), API-6), sharing that code path. Running the
  same bootstrap twice is a no-op.
- **BOOT-3** API keys in bootstrap: the document supplies the key **value**
  via env-style reference (never plaintext committed to the repo), or a
  `create-if-missing` entry whose generated value is printed once to the
  startup log. Existing keys are never overwritten.
- **BOOT-4** Bootstrap failures follow `BUNDLEMCP_BOOTSTRAP_STRICT`:
  `true` → refuse to start (CI/production), `false` (default) → log and
  continue (dev convenience).
- **BOOT-5** Resources created by bootstrap are ordinary resources —
  editable in the UI afterwards; bootstrap does not "own" or re-lock them
  (last write wins, no reconciliation loop — that's a registrar-style
  external agent's job via the API).

## Out of scope

- Continuous reconciliation / GitOps-style drift correction.
- Provisioning users (users come from OIDC — [ADM-2](21-admin-auth.md)).

## Open questions

- None.
