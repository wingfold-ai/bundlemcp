# Proposal

## Why

Admins debug upstreams and endpoints constantly — does the tool exist, what does its schema say, what does a call return
through this endpoint's profile — and today they need the reference MCP inspector running beside the gateway, with
credentials copied out of it. The admin UI's *Inspector* page is a placeholder (`apps/web/app/pages/inspector.vue`).
metamcp shipped a built-in inspector (`../metamcp/apps/frontend/app/[locale]/(sidebar)/mcp-inspector/`, backend
`routers/mcp-proxy.ts`); this change brings a simplified, tools-first version.

`POST /api/v1/upstreams:inspect` already exists, but it is registration inspection (UPS-11: what auth a URL needs
before it is registered), not this interactive tool.

## What Changes

- Management API routes under `/api/v1/inspector/` that connect to a registered upstream, an endpoint of this gateway,
  or an ad-hoc URL with headers, and run `initialize`, `ping`, `tools/list` and `tools/call` on it, streaming progress
  notifications and reporting timings.
- Stored upstream secrets are applied server-side and never reach the browser; ad-hoc URLs pass the egress policy.
- Endpoint targets go through the real public path (authentication, profile, curation, metering) and are audited like
  any client; upstream and ad-hoc calls are logged with `source=inspector` and are not audited.
- The *Inspector* page replaces the placeholder: target picker, capability view, tool list with schemas, a form
  generated from the input schema with a raw-JSON fallback, results, errors, progress and timing.
- `documentation`: DOC-2 — with every reserved surface now built, the operations page's "Not part of this release"
  section is left out rather than listing surfaces that exist.
- `security`'s SEC-1 names inspector ad-hoc targets in the egress policy's scope.

Out of scope (carried from the original spec): browsing resources and prompts in v1 (tools first; member passthrough
survived the scope review, so this is a natural later addition), roots/sampling test panels (consciously skipped), and
saved inspector configurations or collections.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `admin-ui`: adds UI-8..UI-11 — targets, operations, the management-API proxy, and audit/log attribution; UI-1 lists
  the Inspector page instead of a placeholder. On archive, extend the slice's Purpose to mention the inspector.
- `security`: SEC-1 — inspector ad-hoc targets are within the egress policy's scope.
- `documentation`: DOC-2 — the operations page names no admin UI page as a placeholder; its "Not part of this
  release" section is left out when nothing is reserved but unbuilt.

## Impact

- Code: an inspector use case in `application/`, an in-process client for the gateway's own endpoints in
  `infrastructure/fastmcp/` wired in `main/`, a controller under `api/management/controllers/`, DTOs in
  `application/schemas/`, and the Nuxt page.
- API: new routes and DTOs; `cd apps/web && npm run openapi`.
- UI tests: `apps/web/tests/login.spec.ts` asserts the `inspector-placeholder` marker and must assert the real page.
- Docs: `docs/self-hosting/operations.md` (says there is no inspector), a page under `docs/manage/`, and
  `docs/arc42/11-risks-and-technical-debt.md` if it still mentions the inspector's coverage.
- Live logs: `source=inspector` events show up in `add-live-logs`' view once both land; no hard dependency.
- ADR: one new ADR (next free number) for proxying inspector traffic through the management API, with endpoint
  targets dispatched in-process through the public MCP route.
