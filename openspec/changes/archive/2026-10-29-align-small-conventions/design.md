# Design

## Context

See [proposal.md](proposal.md) for why each item matters. This section covers only the current state that shapes the
approach. Line numbers were checked against `main` at `2399dae`.

- **Audit filter.** `AuditFilter` (application, `application/management/audit_filter.py`) is a plain DTO.
  `InMemoryAuditRepository._matches` (infrastructure, `memory/in_memory_audit_repository.py:35-53`) and
  `SqlAlchemyAuditRepository._criteria` (infrastructure, `postgres/audit_repository.py:59-87`) each restate all eleven
  filters. They also differ in `page()` ordering: the fake sorts `(created_at, str(id))` descending (line 14), while SQL
  orders `created_at desc, id asc` (line 24). `page_after()` is id-descending in both.
- **Clock.** `Clock` and `SystemClock` live in `domain/shared/`. `ManualClock` is in `infrastructure/memory/`. The
  direct reads this change covers are:
  - `discovery_service.py:174`
  - `user_service.py:36` and `:76`
  - `valkey/session_store.py:62`, where `touch` stamps `last_active_at` with the wall clock while `SessionSweeper`
    compares against `self._clock.now()`
  - `valkey/paused_invocations.py:29`, where the TTL is `expires_at - time.time()` while `InvocationSweeper` passes
    `self._clock.now().timestamp()`

  The composition root already holds a `clock` (`main/composition_root.py`), and `AppContainer.clock` reaches the
  service providers.
- **Logging.** `configure_logging` (infrastructure, `config/structured_logging.py`) has no exception processor. A
  check against structlog 26.1 shows `log.warning(..., exc_info=True)` renders `"exc_info": true` in `json` and nothing
  else. In `text`, `ConsoleRenderer` defaults to Rich's traceback formatter with `show_locals=True`, and Rich is
  installed as a transitive dependency of FastMCP. A local `secret_token = 'SEKRET123'` was printed verbatim.
  `create_engine` (`postgres/engine.py:15`) does not set `hide_parameters`, so a DBAPI error's message includes the
  bound parameters. The live log handler renders with `json_event_formatter()`, which uses the same shared processors.
  It skips the publisher's own logger, so `live_log_publisher.py` can log its failure without recursing.
- **The five silent handlers** are:
  - `fastmcp/upstream_probe.py:141` (`discovery.listing_failed`)
  - `dispatch/handlers/completion_handler.py:55` (`completion.member_failed`)
  - `upstream_oauth/upstream_token_storage.py:237` and `secret_reencryption.py:80` (`token_encryption.reencrypt_failed`)
  - `valkey/live_log_publisher.py:56` (`live_log.publish_failed`)
- **Server upsert.** `ServerService.upsert` (`application/management/server_service.py:30-76`) does three things:
  - It builds the new `McpServer` with the `send_identity_header` default from `is_internal_host`.
  - It merges every field: static headers are kept when an empty map is sent, the auth mode is settled from the stored
    headers, and `None` keeps the stored `send_identity_header`, `protocol_mode` and `listing_snapshot`.
  - It runs the cross-resource checks, saves the server and decides whether to probe.
- **Protocol mode.** `protocol_mode` is a plain `str`:
  - The DTO pattern `^(auto|legacy|\d{4}-\d{2}-\d{2})$` is at `server_upsert.py:55-63`.
  - Free text in `server_read.py:46`, `mcp_server.py:51` and `mcp_server_row.py:60`.
  - `discovery_inputs.py:28`.

  `GuardedClientFactory` (`fastmcp/client_factory.py:86,105`) passes the string straight to FastMCP's
  `Client(mode=...)`, whose `ConnectMode` accepts only `"auto"`, `"legacy"` or a modern revision and raises
  `ValueError` otherwise. So `legacy` is the SDK's word. A release that writes any other spelling to the row breaks
  every replica of the previous release that connects to that server. `BootstrapServer` derives from `ServerUpsert`,
  so bootstrap and import share the DTO's validation. Export builds the document from the entity
  (`config_export_service.py:92`).

## Goals / Non-Goals

**Goals:**

- One statement of the audit filter, with a test that fails when the fake and SQL disagree.
- Every service and adapter outside `SystemClock` reads time through an injected `Clock`.
- A logged exception is diagnosable in both formats and can never print a secret held in a local, a rejected input or
  a statement parameter.
- `McpServer` owns its create defaults and update merge.
- `session` is the only spelling of the handshake-only mode in the domain, the API output and the UI. `legacy`
  survives only as an input alias and, for one release, as the stored spelling.

**Non-Goals:**

- Changing what the audit filters match, beyond aligning the `page()` tie-break.
- The clock reads in the tool-call and relay pipeline (see proposal, Not covered).
- Scrubbing every possible secret from exception messages. Messages are rendered, and only the three leak paths found
  here are closed (locals, validation input, SQL parameters).
- Changing the upsert's behaviour. The move is a refactor, and the existing management and API tests pin it.
- Renaming `BUNDLEMCP_LEGACY_PROTOCOL_ENABLED`.

## Decisions

### Audit filter: `matches` on the filter, a column table for SQL

`AuditFilter.matches(record: AuditRecord) -> bool` (application) states the rule over the entity, and the in-memory
repository's `where` calls it. The rule cannot go on `AuditRecord` (domain), because `AuditFilter` is an application
type and the domain imports nothing from application.

The SQL side cannot reuse a Python predicate, so it keeps its own clause builder. The builder is driven by a table
instead of eleven `if` blocks:

- `_EQUALS: dict[str, InstrumentedAttribute]` maps each equality field to its column.
- The two range fields and the tool OR rule are written once, beside the table.

The contract test catches any drift between the two halves:

- `tests/infrastructure/test_audit_repository_contract.py` runs a fixture parametrised over `InMemoryUnitOfWork` and
  `SqlAlchemyUnitOfWork` (sqlite).
- Both get the same seeded records, including two with equal `created_at`.
- It runs a table of filters through `page()` and `page_after()`, one case per field plus the tool rule on both
  names, and asserts identical ids in identical order.

Both repositories then order `page()` by `created_at desc, id desc`, the order `page_after()` and its cursor already
use. OPS-6 says "newest first" and leaves ties open, so only the SQL tie-break moves, and only between records stamped
in the same microsecond.

*Alternatives:*

- A SQLAlchemy-free predicate compiled to both Python and SQL. That is a small query language, and it is too much for
  eleven fields.
- Testing only the fake. That would not catch the next divergence.

### Clock: constructor injection, signatures unchanged

Each covered class takes a required keyword `clock: Clock`, and its single read becomes `self._clock.now()`:

| Class | Layer |
|---|---|
| `DiscoveryService`, `UserService` | application |
| `ValkeySessionStore`, `ValkeyPausedInvocations` | infrastructure |

The paused store uses `self._clock.now().timestamp()` for its float epoch. The contracts (`SessionStore`,
`PausedInvocations`) keep their method signatures, so the api-layer callers (`session_adapter.py`,
`session_stream.py`), which `make-tool-call-order-explicit` is editing, are untouched. The composition root passes its
`clock`, and `get_user_service` passes `container.clock`.

*Alternative:* pass `now` into `touch()` and `pause()`. That is more explicit, but it changes a contract and every
caller in files another change owns, for no gain over a constructor-held clock.

### Exception rendering: one processor in the shared chain

A new processor sits in `_shared_processors()`, so the process log, the `text` renderer and the live-log formatter all
get it. It is the class `TracebackRenderer`, in infrastructure (`config/traceback_renderer.py`). It replaces an event's
`exc_info` with an `exception` string. To build that string it:

- walks `__cause__` and `__context__` (and an exception group's members) as the standard library does, formatting
  each link's frames with `traceback.StackSummary.extract(..., capture_locals=False)`;
- renders a link of that chain that is a Pydantic `ValidationError` as its title plus
  `errors(include_input=False, include_url=False)`, one `loc: msg (type)` line each, instead of `str(exc)`, which
  embeds `input_value`.

*Adjusted during implementation:* the plan was to format a `traceback.TracebackException` directly. It computes every
link's message from `str(exc)` when it is built, and the chained links are plain `TracebackException`s, so a validation
error deeper in the chain could only be rewritten through the private `_str` attribute. The renderer walks the chain
itself instead, using the same public building blocks, so the rule against rejected input holds on every link.

`ConsoleRenderer` is built with `exception_formatter=structlog.dev.plain_traceback`, so even an `exc_info` that
reaches it unprocessed is never handed to Rich. Rich is never used with locals.

`create_engine` sets `hide_parameters=True`, so SQLAlchemy errors read `[SQL parameters hidden due to
hide_parameters=True]`. The Alembic engine in `migrations/env.py` sets it too, because data migrations bind
ciphertexts as well (added during implementation). The five handlers then pass `exc_info=True`.

*Alternatives:*

- structlog's `dict_tracebacks`, whose `ExceptionDictTransformer` defaults to `show_locals=True` and renders
  `exc_value` with `str()`. It would need the same overrides and gives `json` and `text` different shapes.
- Dropping the message entirely. That is safer, but `discovery.listing_failed` without "401 Unauthorized" is not
  diagnosable.
- Leaving `exc_info` off the five handlers. That hides causes, and the real defect, the Rich locals, would remain at the
  44 existing sites.

### Server writes: `register` and `reconfigure` on the entity

The pieces, by layer:

| Piece | Layer | What it holds |
|---|---|---|
| `ServerChanges` | domain (`domain/servers/server_changes.py`) | A frozen `BaseModel` with the write's configurable fields: `description`, `url`, `static_headers`, `forward_headers`, `auth_mode`, `identity_mode`, `send_identity_header: bool \| None`, `protocol_mode: ProtocolMode \| None` and `listing_snapshot: ListingSnapshotMode \| None`. `None` means "keep". |
| `McpServer.register(name, changes)` | domain | A classmethod that applies the create defaults (`send_identity_header` from `is_internal_host` when `None`) and then `reconfigure` |
| `McpServer.reconfigure(changes)` | domain | The merge: an empty `static_headers` keeps the stored ones, the auth mode is settled through `ServerAuthMode.settled`, and `None` keeps the stored value |
| `ServerUpsert.changes()` | application | Maps the DTO onto the value object |

`ServerService.upsert` keeps what spans resources or does I/O:

- the self-reference check on a URL change
- the per-user policy
- the grant check
- the save
- the probe decision, by comparing `discovery_inputs` before and after

The domain tests pin the merge rules on pure objects. The existing `test_management_on_fakes.py`,
`test_server_setup_on_fakes.py` and API tests pin that the service's behaviour is unchanged.

*Alternative:* have `reconfigure` return whether a probe is needed. It reads well, but the probe decision also depends
on `last_probe_succeeded` and is a service policy (ADR-0043), so the comparison stays in the service.

### Protocol mode: a domain type, an SDK translation, a row translation for one release

- **Domain** (`domain/servers/protocol_mode.py`): `NegotiationMode(StrEnum)` with `AUTO = "auto"` and
  `SESSION = "session"`, `PinnedRevision = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]`, and
  `ProtocolMode = NegotiationMode | PinnedRevision`. `McpServer.protocol_mode`, `DiscoveryInputs.protocol_mode` and
  `ServerRead.protocol_mode` use `ProtocolMode`. Pydantic's smart union validates `"auto"` and `"session"` as the enum.
  OpenAPI then shows `anyOf: [enum [auto, session], string pattern]`, and openapi-typescript generates
  `"auto" | "session" | string`.
- **Input alias** (application): `ServerUpsert.protocol_mode` is `ProtocolMode | None` with a `mode="before"`
  validator that maps `"legacy"` to `"session"`. The published enum does not list `legacy`, and the field description
  calls it a deprecated alias. `BootstrapServer` inherits the validator, so bootstrap and import accept it too.
- **SDK translation** (infrastructure, `fastmcp/connect_mode.py`): `connect_mode(mode: ProtocolMode) -> ConnectMode`
  maps `SESSION` to `"legacy"`, `AUTO` to `"auto"` and a revision to itself. `GuardedClientFactory` calls it in both
  constructors. The SDK's word stays at the SDK boundary, as `design-principles.md` §1 allows.
- **Row translation for one release** (infrastructure, `postgres/server_repository.py`): `_to_row` writes `session`
  as `legacy`, and `_to_entity` reads `legacy` as `session`. This expand step keeps every stored value readable by the
  previous release, which passes the column straight to the SDK (DEP-5). The contraction, in a follow-up change one
  release later, is an Alembic revision that rewrites the column to `session` and removes the translation.

*Alternatives:*

- **`handshake` as the name.** It is intrinsic too, and the specs say "handshake era". But ADR-0035 renamed
  `Era.HANDSHAKE` to `ProtocolEra.SESSION` so that the pair reads "stateless/session", and the upstream setting should
  use the same word as the edge.
- **Migrating the rows in this release**, as revision `0009` did for profiles (ADR-0047). That breaks DEP-5. ADR-0047
  recorded that exception for its case, and nothing here justifies another.
- **A full enum including pinned dates.** The set of revisions the SDK accepts lives in the SDK, which the domain may
  not import.
- **No alias,** as ADR-0045 and ADR-0047 chose for their renames. The conformance harness, the stdio-sidecar guide and
  any bootstrap file in the wild send `legacy`, and an alias costs one validator.

## Risks / Trade-offs

- [A previous-release replica reads a row written by this release] → the row translation stores `legacy`, so it reads
  exactly what it wrote before.
- [`config_fingerprint` changes for `session` servers, from `legacy` to `session` in the digest] → each replica opens
  one new pooled upstream session for such a server after the upgrade (SES-9). It is the same effect as any config
  change, and it is harmless.
- [An export from this release is imported into the previous release] → that release rejects `session` with `422`.
  Moving documents backwards is not supported, and the upgrade notes say so.
- [Tracebacks enlarge log lines] → only at the 49 sites that ask for one, all on failure paths. The live log's stream
  stays capped by entry count (OPS-14).
- [An exception message carries a secret by other means, for example a credential in an upstream URL's query string]
  → not closed here. URLs are returned in full by the server read API today, so this is not a new exposure. It is
  listed as an open question rather than solved with a guessing scrubber.
- [The tie-break change shifts a page boundary] → only between audit records with identical microsecond timestamps,
  and keyset pagination (`page_after`) already used this order.
- [`split-admin-ui-pages` and this change both edit `pages/upstreams/[name].vue`] → the UI edit here is one `<option>`
  and the label helper, and whichever lands second rebases.

## Migration Plan

Deploy the new image. No schema migration, and nothing stored changes spelling in this release. Rollback is the
previous image. The follow-up contraction ships its Alembic revision with a downgrade that rewrites `session` back to
`legacy`.

## Open Questions

- Should a pinned `protocol_mode` be checked against the revisions the MCP client supports? A handshake-era date such
  as `2025-06-18` passes the pattern today and only fails at connect, when the SDK raises `ValueError`. That needs an
  application-level port onto the SDK's version list. It is independent of the rename and can be its own change.
- Should exception messages pass through a query-string scrubber? This depends on whether upstream URLs are ever
  treated as secret. Today they are not.
- UPS-1's scenario "Removing the last static header settles on none" is not implemented: an empty `static_headers` map
  keeps the stored headers (`server_service.py:56`), and no API field clears them. `reconfigure` preserves today's
  behaviour. Whether to add an explicit clear, or correct the scenario, is a separate change.
