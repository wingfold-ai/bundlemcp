# 15 — Endpoint profiles

**Status:** Accepted · **Origin:** new (the reason bundlemcp supports N endpoints per bundle)

## Summary

A profile adapts one bundle to the quirks of a consuming client. Profiles are **built-in, named presets** (not a
user-defined plugin system in v1): they constrain auth modes and transform the tool surface. First shipping profiles:
`default`, `claude`, `chatgpt`.

## Requirements

- **PROF-1** `default`: passthrough. No tool transformation; any auth mode allowed.
- **PROF-2** `claude` (claude.ai remote MCP connector):
  - requires `oauth` in `auth_modes` (validated on endpoint write);
  - passthrough tools;
  - guarantees the OAuth discovery surface claude.ai needs: dynamic client registration, PKCE, `.well-known` metadata
    ([20-oauth-server.md](20-oauth-server.md)).
- **PROF-3** `chatgpt` (ChatGPT connector, which restricts/behaves differently toward write tools):
  - **re-annotates write tools as read-safe**: every served tool's annotations are rewritten so the client treats it as
    read-only — `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint` preserved. The tools
    **still perform their real (write) operations upstream**; only the presented annotations change. This is the
    user-chosen semantic: expose everything, shaped to what the client accepts.
  - The UI MUST display a clear warning on chatgpt-profile endpoints that annotations no longer reflect true tool
    behavior, and the audit log records calls normally so writes remain traceable.
  - Explicit per-tool overrides ([TM-4](13-tool-management.md)) win over the profile rewrite.
- **PROF-4** Profile transforms are implemented as middleware ([31-middleware.md](31-middleware.md)) applied at the
  endpoint layer — after bundle curation, before serving — in both `tools/list` and `tools/call` validation.
- **PROF-5** Adding a new profile is a code change implementing a small interface (constrain-auth + transform-tools);
  profiles are listed by the management API so the UI stays data-driven.
- **PROF-6** Profile × auth-mode validation matrix (enforced on endpoint create/update):

  | Profile | Allowed `auth_modes` |
  |---|---|
  | `claude` | exactly `[oauth]` |
  | `chatgpt` | must include `oauth` or `api_key`; bare `[none]` rejected |
  | `default` | any valid combination per [EP-3](14-endpoints.md) |

## Out of scope

- User-defined/scriptable profiles (revisit if built-ins prove insufficient).
- ChatGPT's `search`/`fetch` deep-research connector contract (dropped in scoping; can become a fourth profile later
  without structural change).

## Open questions

- Verify against current ChatGPT connector behavior (July 2026) which annotation set it enforces; adjust PROF-3's exact
  rewrite map at implementation time.
