# 60 — Admin UI

**Status:** Accepted · **Origin:** improvement (Next.js → Nuxt 4, scope trimmed)

## Summary

A Nuxt 4 + Nuxt UI v4 single-page admin app covering the full management
surface. It is a pure client of the management API
([40-management-api.md](40-management-api.md)) with generated TypeScript types
([ARC-4](01-architecture.md)). English-only, light/dark theme.

## Requirements

- **UI-1 Pages**:
  - **Servers** — list w/ health badges; detail: config, secret header
    editing (write-only), forward-headers, upstream OAuth connect status
    ([UPO-5](23-upstream-oauth.md)), discovered tools, refresh/prune, probe.
  - **Bundles** — list; detail: member servers (add/remove/enable), tool
    curation table (enable toggles, inline overrides, stale/overridden
    badges — [TM-5](13-tool-management.md)), endpoints of this bundle.
  - **Endpoints** — list; detail: bundle, profile (with chatgpt-profile
    warning [PROF-3](15-endpoint-profiles.md)), auth modes, rate limits,
    connection card (copy-paste URL + per-client setup instructions —
    [EP-7](14-endpoints.md)).
  - **API keys** — create (one-time value display), scope, kind,
    activate/deactivate ([22-api-keys.md](22-api-keys.md)).
  - **Audit** — filterable table + CSV ([AUD-6](50-audit-log.md)).
  - **Live logs** — stream view ([52-live-logs.md](52-live-logs.md)).
  - **Inspector** — ([53-inspector.md](53-inspector.md)).
  - **Users** — list of provisioned users, admin flag display, deactivate
    action ([ADM-6](21-admin-auth.md)), per-user OAuth consents with revoke
    ([OAS-11](20-oauth-server.md)).
  - **Settings** — runtime `Config` editing, export/import
    ([EXP-6](42-export-import.md)).
- **UI-2** Auth: OIDC login redirect ([21-admin-auth.md](21-admin-auth.md));
  all routes behind it; non-admin users get a "no access" page.
- **UI-3** Frontend API layer: generated client from
  `/api/v1/openapi.json`; no hand-written DTO types; TanStack Query (or
  Nuxt-native equivalent) for caching/invalidation.
- **UI-4** Form validation mirrors backend rules (generated from the OpenAPI
  constraints where possible) so users see slug/uniqueness errors before
  submitting.
- **UI-5** The web container is optional at runtime: the gateway is fully
  operable via API alone ([API parity — 40-management-api.md](40-management-api.md)).

## Out of scope

- i18n (decision log), mobile-optimized layouts, theming beyond the brand
  tokens (the wordmark teal as the primary colour, the documentation site's
  gray surfaces, the logo in the header and as favicon) applied through Nuxt
  UI's design tokens — no per-component styling.

## Open questions

- None.
