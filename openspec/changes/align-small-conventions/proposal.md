# Proposal

## Why

The 2026-10-29 code audit found five places where the code has drifted from the repo's own conventions. Each one is
small, and each one has already hidden a defect:

- **S10: the audit filter is written twice.** `InMemoryAuditRepository._matches` and
  `SqlAlchemyAuditRepository._criteria` each implement the eleven audit filters, including the rule that a tool filter
  matches the upstream or the client-visible name. Nothing tests the fake. The two already disagree: `page()` breaks a
  tie on `created_at` by id descending in the fake and by id ascending in SQL.
- **S15: services bypass the injected `Clock`.** `DiscoveryService`, `UserService`, the Valkey session store and the
  Valkey paused-invocation store read `utcnow()` or `time.time()` directly. Their time-dependent behaviour cannot be
  driven by `ManualClock`.
- **S18: exceptions are logged without their cause.** Five `except Exception` blocks log a warning without
  `exc_info`. Checking whether adding it is safe turned up something worse. With the current logging setup, `exc_info`
  renders nothing at all in the `json` format: the line says `"exc_info": true` and nothing more. In the `text` format
  the full traceback is rendered with **every frame's local variables**, so a token or decrypted secret held in a local
  is written to standard error. That breaks OPS-8 and SEC-10 at the 44 call sites that already pass `exc_info=True`.
  SQL errors would also print their statement parameters, because the engine does not hide them.
- **S20: `ServerService.upsert` is anemic.** The field-by-field merge, the defaults and the rule that settles the auth
  mode all sit in the service (`server_service.py:30-76`), not on `McpServer`.
- **S22: `protocol_mode` publishes the temporal name `legacy`.** The value is part of the management API, the
  bootstrap and export documents and the admin UI. Its OpenAPI type is a bare `string | null` with a pattern, so the
  generated TypeScript type tells a client nothing. The edge already renamed the same idea from `Handshake` to `Session`
  ([ADR-0035](../../../docs/adr/0035-front-controller-protocol-adapters-and-admission-pipeline.md)).

## What Changes

- **One audit filter rule.** `AuditFilter.matches(record)` is the single in-process statement of the filter, and the
  in-memory repository uses it. The SQL repository builds its clauses from a field-to-column table, and the tool rule
  appears once. A contract test runs the same filters and orderings against both repositories. Both now break ties by
  id descending.
- **The injected clock everywhere outside `SystemClock`.** `DiscoveryService`, `UserService`,
  `ValkeySessionStore` and `ValkeyPausedInvocations` take a required `clock: Clock`, and the composition root and the
  service provider pass the existing one. No observable behaviour changes.
- **Tracebacks that are useful and safe.** A logged exception is rendered in both formats as its type, message and
  stack frames, never its local variables. A Pydantic validation error is rendered without the input it rejected, and
  SQL errors carry no statement parameters. The five silent `except Exception` blocks pass `exc_info`.
- **`McpServer.register()` and `McpServer.reconfigure(ServerChanges)`.** The create defaults and the update merge move
  onto the entity. A frozen `ServerChanges` value object carries the write. The service keeps the cross-resource checks,
  the save and the probe decision. Behaviour is unchanged.
- **`protocol_mode: session` replaces `legacy`** (UPS-10, modified). The API, the bootstrap and import documents accept
  `legacy` as a deprecated alias and store it as `session`. Reads and exports return `session`. The OpenAPI document
  publishes the named modes as an enum next to the pinned-revision pattern. The admin UI offers `session` through the
  regenerated types. Rows stored as `legacy` read as `session`. The stored spelling stays `legacy` for one release so
  that the previous release, which passes the value straight to the MCP client, can still read every row during a
  rolling update (DEP-5).
- **OPS-8 modified:** a logged exception carries its traceback without local variables, rejected input or SQL
  parameters.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `upstreams`: UPS-10 (`session` is the name of the handshake-only mode; `legacy` is a deprecated input alias; reads
  return `session`; the named modes are an enum in the published schema).
- `operations`: OPS-8 (logged exceptions carry a traceback, and never local variables, rejected input or SQL
  parameters).

## Impact

- **Resolves:** audit findings S10, S15 (in part), S18 (in part), S20 and S22 (2026-10-29). No GitHub issue.
- **Code:**
  - domain: `domain/servers/mcp_server.py`, new `domain/servers/server_changes.py` and
    `domain/servers/protocol_mode.py`, and `domain/servers/discovery_inputs.py`.
  - application: `application/management/audit_filter.py`, `server_service.py` and `user_service.py`,
    `application/discovery/discovery_service.py`, `application/upstream_oauth/upstream_token_storage.py` and
    `secret_reencryption.py`, and the DTOs `application/schemas/servers/server_upsert.py` and `server_read.py`.
  - infrastructure: `memory/in_memory_audit_repository.py`, `postgres/audit_repository.py`,
    `postgres/server_repository.py`, `postgres/rows/mcp_server_row.py` (its description), `postgres/engine.py`,
    `config/structured_logging.py` and a new exception renderer beside it, `valkey/session_store.py`,
    `valkey/paused_invocations.py`, `valkey/live_log_publisher.py`, `fastmcp/upstream_probe.py`,
    `fastmcp/client_factory.py` and a new `fastmcp/connect_mode.py`.
  - api: `api/mcp/dispatch/handlers/completion_handler.py` and `api/http/service_providers.py`.
  - main: `main/composition_root.py`.
- **API:** `protocol_mode` in `ServerUpsert` and `ServerRead` changes its published schema (an enum of `auto` and
  `session`, or a revision date). A read that returned `legacy` now returns `session`. Clients that send `legacy` keep
  working. `apps/web/openapi.json` and `apps/web/types/api.d.ts` are regenerated.
- **Admin UI:** `ServerRegistration.vue` and `pages/upstreams/[name].vue` offer `session`. `split-admin-ui-pages`
  also edits these pages, so whichever change lands second rebases.
- **Logs:** lines logged with an exception now carry an `exception` field holding the traceback. In `text` format the
  traceback no longer shows local variables.
- **Docs:** `docs/manage/servers.md`, `docs/guide/upstream-server-settings.md`, `docs/connect/stdio-sidecar.md`, the
  Notes entity list in `openspec/specs/architecture/spec.md`, and `tests/conformance/run_conformance.py`. No ADR: the
  rename applies ADR-0035's naming to the upstream side, and the alias follows the expand/contract rule DEP-5 already
  sets.
- **Not covered:**
  - The clock reads in `api/mcp/tool_call/tool_call.py:364`, `api/mcp/dispatch/handlers/input_required_bridge.py:161`
    and `api/mcp/relay/request_state.py:85`. The first two stamp a requestState's expiry and the third checks it, so
    all three should move together. The two stamping files belong to `make-tool-call-order-explicit`, and
    `request_state.py`'s only callers are the bridge and `tools_call_handler.py`, so the three are left to that change
    or a follow-up.
  - The missing `exc_info` at `member_fanout.py:194`, which `make-tool-call-order-explicit` removes.
  - The contraction step: a migration that rewrites stored `legacy` rows to `session` and drops the row-level
    translation. It ships one release later, per DEP-5.
  - Removing the `legacy` input alias. That is a breaking change for a later major release.
  - Renaming `BUNDLEMCP_LEGACY_PROTOCOL_ENABLED`. It is a settings deprecation in another slice (protocol, PROT-13),
    and `design-principles.md` already tracks it as the one open item.
  - Validating a pinned revision against the revisions the MCP client supports. See design, Open Questions.
