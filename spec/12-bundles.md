# 12 — Bundles

**Status:** Accepted · **Origin:** metamcp carry-over (metamcp: "namespaces")
**Prior art:** `../metamcp/apps/backend/src/lib/metamcp/metamcp-proxy.ts`, `utils.ts` (sanitizeName), `tool-name-parser.ts`

## Summary

A bundle composes N upstream servers into one virtual MCP server. Tool names
are prefixed with the server name to stay collision-free; calls are routed back
to the owning upstream by parsing the prefix.

## Requirements

- **BND-1** A bundle has a unique slug-safe `name`, a `description`, and an
  ordered set of member servers. The `description` is served as the MCP
  `instructions` field of the virtual server.
- **BND-2** Tool naming: every exposed tool is `<server_name>__<tool_name>`
  (double underscore separator). Server names are already slug-safe
  ([DOM-4](02-domain-model.md)); the combination is guaranteed unique because
  `(server, tool)` is unique. Prefixing happens before overrides
  ([13-tool-management.md](13-tool-management.md)) are applied.
- **BND-3** Call routing MUST parse the prefix, resolve the member server,
  verify the tool is enabled in this bundle, and forward the call with the
  original (un-prefixed, un-overridden) tool name.
- **BND-4** `BundleServer.enabled=false` removes all of a server's tools from
  the bundle's `tools/list` and blocks calls to them, without deleting the
  membership or its `BundleTool` curation.
- **BND-5** A bundle MUST NOT include bundlemcp's own endpoints as member
  servers (self/circular reference guard, validated at membership creation
  against the endpoint URL set of this instance).
- **BND-6** Bundle CRUD + membership management MUST be available in the
  management API and UI.
- **BND-7** Changes to a bundle (membership, enable flags, overrides) MUST
  take effect for new requests without a gateway restart; live sessions pick
  up changes on their next `tools/list` and SHOULD receive a
  `notifications/tools/list_changed` when the serving session supports it.
- **BND-8** Resources and prompts of member servers are passed through with
  the same prefixing scheme where names collide; v1 treats tools as the
  curated surface and resources/prompts as best-effort passthrough.

## Out of scope

- Nested bundles (a bundle containing a bundle).
- Per-bundle tool renaming beyond overrides.

## Open questions

- Whether `BND-8` passthrough for prompts/resources is worth keeping in v1 at
  all, or bundles should be tools-only until a use case appears.
