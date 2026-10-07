# 13 — Tool management (per-bundle enable/disable + overrides)

**Status:** Accepted · **Origin:** metamcp carry-over **Prior art:**
`../metamcp/apps/backend/src/lib/metamcp/metamcp-middleware/filter-tools.functional.ts`, `tool-overrides.functional.ts`,
`namespace_tool_mappings`

## Summary

Admins curate how a bundle presents its tools: hide tools entirely, or override a tool's public name, title,
description, and annotations. Curation is per-bundle — the same server can present differently in different bundles.

## Requirements

- **TM-1** Each `(bundle, tool)` pair has `enabled` (default true) and optional overrides for `name`, `title`,
  `description`, `annotations` ([02-domain-model.md](02-domain-model.md), `BundleTool`).
- **TM-2** Disabled tools MUST be absent from `tools/list` **and** rejected on `tools/call` with a standard MCP error —
  enforcement in both paths, as middleware ([31-middleware.md](31-middleware.md)).
- **TM-3** Name overrides replace the prefixed name (`server__tool` → `override_name`); the router MUST map override
  names back to the origin server/tool on call. Override names MUST be unique within a bundle (validated on write
  against other overrides and prefixed names).
- **TM-4** Annotation overrides are a shallow merge over the upstream annotations (set a key to `null` to remove it).
  This is the same mechanism the ChatGPT profile uses programmatically
  ([15-endpoint-profiles.md](15-endpoint-profiles.md)); explicit per-tool overrides win over profile rewrites.
- **TM-5** Curation UI: the bundle detail page lists all member tools with enable toggles and inline override editing,
  flagging overridden tools and stale tools ([DISC-3](11-tool-discovery.md)).
- **TM-6** All curation operations available via management API.

## Out of scope

- Editing tool **input schemas** (only name/title/description/annotations).

## Open questions

- None.
