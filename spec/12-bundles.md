# 12 — Bundles

**Status:** Accepted · **Origin:** metamcp carry-over (metamcp: "namespaces") **Prior art:**
`../metamcp/apps/backend/src/lib/metamcp/metamcp-proxy.ts`, `utils.ts` (sanitizeName), `tool-name-parser.ts`

## Summary

A bundle composes N upstream servers into one virtual MCP server. Tool names are prefixed with the server name to stay
collision-free; calls are routed back to the owning upstream by parsing the prefix.

## Requirements

- **BND-1** A bundle has a unique slug-safe `name`, a `description`, and an ordered set of member servers. The
  `description` is served as the MCP `instructions` field of the virtual server.
- **BND-2** Tool naming: every exposed tool is `<server_name>__<tool_name>` (double underscore separator). Server names
  are slug-safe and MUST NOT contain `__` ([DOM-4](02-domain-model.md)), so parsing is unambiguous even when the
  upstream tool name itself contains `__`: **split on the first `__`** — everything after it is the tool name. The
  combination is guaranteed unique because `(server, tool)` is unique. Prefixing happens before overrides
  ([13-tool-management.md](13-tool-management.md)) are applied.
- **BND-3** Call routing MUST parse the prefix (first-`__` rule, or resolve an override name via its `BundleTool`
  mapping first — [TM-3](13-tool-management.md)), resolve the member server, verify the tool is enabled in this bundle,
  and forward the call with the original (un-prefixed, un-overridden) tool name.
- **BND-4** `BundleServer.enabled=false` removes all of a server's tools from the bundle's `tools/list` and blocks calls
  to them, without deleting the membership or its `BundleTool` curation.
- **BND-5** A bundle MUST NOT include bundlemcp's own endpoints as member servers (self/circular reference guard,
  validated at membership creation against the endpoint URL set of this instance).
- **BND-6** Bundle CRUD + membership management MUST be available in the management API and UI.
- **BND-7** Changes to a bundle (membership, enable flags, overrides) MUST take effect for new requests without a
  gateway restart; live sessions pick up changes on their next `tools/list` and SHOULD receive a
  `notifications/tools/list_changed` when the serving session supports it.
- **BND-8** Resources and prompts of member servers are **uncurated passthrough** (tools are the curated surface); they
  are fetched **live** from members per request and are not cached ([DISC](11-tool-discovery.md)). Routing rules:
  - **Prompts** carry a name, so they are **always prefixed** `<server_name>__<prompt_name>` (BND-2 scheme);
    `prompts/get` and completion prompt-refs de-prefix on the first `__` to find the owning member.
  - **Resources** are keyed by opaque URI, not a prefixable name, so URIs are passed through **unchanged**.
    `resources/list` (and `resources/templates/list`) merge members' entries verbatim, de-duplicating by URI (first
    enabled member wins, collisions logged). `resources/read`, `resources/subscribe`, and resource-template completions
    resolve the owning member by **fan-out** — trying enabled members in order and taking the first that owns the URI.
  - Completions are routed per [PROT-9](32-protocol-passthrough.md).
- **BND-9** The capability set the bundle advertises at `initialize` is computed per
  [PROT-11](32-protocol-passthrough.md).
- **BND-10** Bundle `name` is the natural key for export/bootstrap upserts ([EXP-3](42-export-import.md),
  [BOOT-2](41-bootstrap.md)) — the UI/API MUST warn on rename that external automation keyed on the old name will treat
  it as a new bundle.
- **BND-11** A bundle also has an `overview`: a long-form, admin-managed description written for the person browsing the
  catalogue, separate from `description` because that one is sent to a model as the MCP `instructions` (BND-1) and must
  stay short. The catalogue shows the overview together with the tools the bundle serves, after curation
  ([TM-3](13-tool-management.md)), so a user can see what they are connecting before they connect it. Each tool is shown
  by its title and description, the two fields written for a reader; the prefixed name (BND-2) is how a model addresses
  the tool, so it is not shown unless the tool has no title and nothing else identifies it. Both are readable only
  through an endpoint the caller could actually use; a bundle with no OAuth endpoint is reported as not found rather
  than forbidden.

## Out of scope

- Nested bundles (a bundle containing a bundle).
- Per-bundle tool renaming beyond overrides.

## Implementation

BND-8/BND-9 **implemented** ([ADR-0021](../docs/adr/0021-mcp-surface-completion.md)): prompts/resources/completions are
live passthrough with no cache or curation tables; the prefix/URI routing above is enforced in
`application/serving/bundle_view_loader.py` (`resolve_prompt`) and `api/mcp/handlers/` (fan-out handlers). Capability
aggregation reads a per-server `capabilities` snapshot captured at discovery
([DISC](11-tool-discovery.md)).

## Open questions

- ~~Whether `BND-8` passthrough for prompts/resources is worth keeping in v1.~~ **Resolved:** kept — consistent with the
  full-fidelity proxy decision ([32-protocol-passthrough.md](32-protocol-passthrough.md), ADR-0008).
