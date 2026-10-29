# Proposal

## Why

The repo rule is that nothing crosses a layer as a tuple or an untyped dict (ADR-0024), and that data read from outside
round-trips through Pydantic. Five places still break it. Each one fails late, if at all, when a key is misspelled or
a shape drifts. The 2026-10-29 code audit found them (findings S7, S9, S14, S16 and S19):

- **S7: upstream OAuth client metadata is a `dict[str, Any]`.** `UpstreamOAuthClient.metadata_`
  (`domain/upstream_oauth/upstream_oauth_client.py:20`) holds the authorization server's endpoints plus three
  gateway keys (`identification`, `grant_type`, `step_up_scopes`). Five modules read and write it by string key:
  - `application/management/upstream_oauth_config_service.py:67-97`
  - `application/upstream_oauth/upstream_token_storage.py:159-208`
  - `application/upstream_oauth/upstream_connect_flow.py:48-50`
  - `application/management/server_service.py:83`
  - `application/management/config_export_service.py:101-120`

  `UpstreamClientConfig.metadata` (`domain/upstream_oauth/upstream_client_config.py:23`) carries the same dict on, and
  its properties probe it with `.get(...)`.
- **S9: raw MCP capability dicts are walked in the domain.** These modules probe nested dicts with
  `.get(...) or {}`:
  - `aggregate_capabilities` (`domain/bundles/bundle_capabilities.py:9`, complexity D/23)
  - `McpServer.advertises` and `accepts_resource_subscriptions` (`domain/servers/mcp_server.py:108-115`)
  - `PooledUpstreamSessions._listen_filter` (`infrastructure/fastmcp/pooled_upstream_sessions.py:400-413`)

  `McpServer.capabilities` and `ProbeResult.capabilities` are typed bare `dict`.
- **S14: `RuntimeConfig.current(key: str) -> Any` and `get(key: str) -> Any` are stringly typed**
  (`application/serving/runtime_config.py:37-55`). A misspelled key fails at runtime, and every caller casts the
  `Any` it gets back (`int(...)` in `api/http/providers.py:57`, `upstream_health.py:47`, `audit_purger.py:47`).
- **S16: repository `page()` returns `tuple[int, list[T]]`.** There are 23 such signatures across the contracts,
  the Postgres adapters and the in-memory fakes, starting at `application/contracts/persistence/repository.py:36`.
  Callers unpack it positionally (`total, rows = ...`, `_, servers = ...`).
- **S19: the `server.json` importer parses a third-party document by hand.**
  `ServerJsonImporter.draft` (`application/management/server_json_importer.py:21`, complexity C/17) takes a
  `dict[str, Any]` and probes it with `isinstance` and `.get(...)`.

## What Changes

The change has five independent parts. Each can merge on its own, in any order.

- **Typed pages.** A generic `PageSlice[T]` model in the application's persistence contracts (`items`, `total`)
  replaces the tuple in every `page`/`page_for_*` signature and in their callers. `Page.of` takes it.
- **Typed runtime settings.** A frozen `RuntimeSettings` model in `domain/config/` has one typed field per
  runtime-tunable key, and the key registry is derived from it. `RuntimeConfig` gains `snapshot` (no I/O) and
  `settings()` (loads on demand), both returning `RuntimeSettings`. These replace `current(key)` and `get(key)`, and
  the unused `all()` is removed. The management API still addresses keys by name, with the same validation messages.
- **Lenient `server.json` models.** `RegistryServerDocument`, `RegistryRemote` and `RegistryHeader` ignore unknown
  keys and skip list entries that are not objects, as the hand-written code does today. `ServerJsonImporter` validates
  the posted document into them and drafts from typed fields. The request DTO stays `document: dict[str, Any]`, so the
  published API does not change.
- **Typed capabilities.** A frozen `ServerCapabilities` value object in `domain/servers/` replaces the bare dict on
  `McpServer` and `ProbeResult`. It has typed `tools`, `prompts`, `resources`, `completions` and `logging` members
  and keeps every other key it was given. It serialises back to exactly the snapshot it was built from, so the stored
  JSON column and `ServerRead.capabilities` are unchanged. Bundle capability aggregation becomes a fold over
  `ServerCapabilities.union`.
- **Typed client metadata.** A frozen `UpstreamClientMetadata` value object in `domain/upstream_oauth/` replaces
  `UpstreamOAuthClient.metadata_` and `UpstreamClientConfig.metadata`. It holds the identification, the grant, the
  step-up scopes and the remembered endpoints (an `UpstreamMetadata`, or none). It reads every JSON shape the gateway
  has ever stored and writes the same flat shape. The string-key constants `IDENTIFICATION_KEY`, `GRANT_KEY` and
  `STEP_UP_KEY` are removed.
- No behaviour changes, no API changes, no migration: the stored JSON columns keep their shape. This change carries
  no spec delta (`skip_specs`). One edge, documents that violate the `server.json` schema's own types, is discussed
  under the design's open question.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. A pure refactor towards ADR-0024 (value objects) and ADR-0025 (repositories). The requirements it touches keep
their wording and are pinned by tests: PROT-11 and BND-27 (capability aggregation), UPS-22 (capability snapshot),
UPS-15 (`server.json` import), UPS-25, UPS-34 and UPS-35 (upstream OAuth client and step-up), SEC-7 (request size
from the snapshot), SES-8 (upstream connection caps), MGMT-5 (pagination) and MGMT-16 (the upstream OAuth client in
the export document).

## Impact

- **Resolves:** audit findings S7, S9, S14, S16 and S19 (2026-10-29). No GitHub issue.
- **Code:**
  - `domain/`:
    - `servers/` (new `server_capabilities.py`; `mcp_server.py`)
    - `bundles/bundle_capabilities.py`
    - `upstream_oauth/` (new `upstream_client_metadata.py`; `upstream_oauth_client.py`, `upstream_client_config.py`)
    - `config/` (new `runtime_settings.py`; `config_registry.py`)
  - `application/`:
    - `contracts/persistence/` (new `page_slice.py`; seven repository contracts)
    - `contracts/upstream/upstream_probe.py`
    - `schemas/common/page.py`
    - `schemas/servers/server_read.py` (mapping only, the DTO is unchanged)
    - `serving/runtime_config.py` and `discovery/upstream_health.py`
    - `management/`: the importer, the server, upstream OAuth config, export, endpoint and paging services, and a new
      `server_json/` package for the document models
    - `upstream_oauth/`: `upstream_token_storage.py` and `upstream_connect_flow.py`
  - `infrastructure/`:
    - `postgres/`: `sqlalchemy_repository.py` and the nine paging adapters
    - `memory/`: the paging fakes
    - `fastmcp/`: `upstream_probe.py` and `pooled_upstream_sessions.py`
  - `api/`:
    - `http/providers.py`
    - `jobs/audit_purger.py`
    - `mcp/protocol/cache_hints.py`
    - `mcp/dispatch/handlers/initialize_handler.py` and `server_discover_handler.py`
  - `main/composition_root.py`
- **API:** none. No DTO changes, so `apps/web/openapi.json` and the generated types stay as they are.
- **Data:** none. No migration: the `capabilities` and `upstream_oauth_clients.metadata` JSON columns keep their
  shape, and every shape stored so far still loads (see design).
- **Docs:** `.claude/docs/design-principles.md` names `RuntimeConfig.current`, which becomes `RuntimeConfig.snapshot`.
  No ADR: this applies ADR-0024 and ADR-0025 and decides nothing new.
- **Not covered:**
  - S8 (typed upstream notifications) and S11 (the pool's state machine) are separate changes. They touch
    `pooled_upstream_sessions.py` too, so whichever merges second rebases.
  - N10 (the probe's listing pager returns a tuple) stays inside one infrastructure module and crosses no layer.
  - N13 (`SignalEnvelope(**json.loads(...))`) is a one-line fix with no relation to these models.
  - The client-side capability dicts (`SessionRecord.client_capabilities`, `RequestContext.client_capabilities`) and
    the inspector's verbatim `capabilities` are passed through without being walked by domain logic.
