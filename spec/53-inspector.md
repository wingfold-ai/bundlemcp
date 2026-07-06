# 53 — MCP inspector

**Status:** Accepted · **Origin:** metamcp carry-over (simplified)
**Prior art:** `../metamcp/apps/frontend/app/[locale]/(sidebar)/mcp-inspector/`, backend `routers/mcp-proxy.ts`

## Summary

A built-in inspector page: connect to any registered server or any bundlemcp
endpoint, list its tools, and execute test calls — the debugging loop admins
use constantly, without leaving the UI or standing up the reference
inspector.

## Requirements

- **INS-1** Targets: (a) any registered upstream server (connect using its
  stored config — headers/OAuth applied server-side, secrets never sent to
  the browser), (b) any bundlemcp endpoint (exercising the full public path:
  profile, curation, middleware), (c) an arbitrary URL + headers entered
  ad hoc.
- **INS-2** Capabilities: initialize + capability display, `ping`,
  `tools/list` (with schema view), `tools/call` with a form generated from
  the input schema (Pydantic/JSON-Schema driven) and raw-JSON fallback,
  response + error display (incl. progress events), request timing.
- **INS-3** The browser never talks to upstreams directly: the management API
  proxies inspector traffic (admin-authenticated, [API-2](40-management-api.md)),
  so stored secrets stay server-side and CORS stays closed. Ad-hoc URL
  targets pass the egress policy ([SEC-1/SEC-2](70-security.md)).
- **INS-4** Inspector calls against **endpoints** go through the real public
  path and are audited like any client ([AUD-1](50-audit-log.md)); calls
  against raw servers are marked `source=inspector` in logs and are NOT
  audit records (they bypass endpoint context).

## Out of scope

- Resources/prompts browsing in v1 (tools first; BND-8 passthrough survived
  the scope review, so this is a natural later addition).
- Roots/sampling test panels (metamcp's inspector had them; consciously
  skipped).
- Saved inspector configurations/collections.

## Open questions

- None.
