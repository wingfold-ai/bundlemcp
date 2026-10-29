# Design

## Context

See [proposal.md](proposal.md) for the five findings. Three facts about the code shape every decision below:

- **The row mapping is generic.** `SqlAlchemyRepository` (`infrastructure/postgres/sqlalchemy_repository.py:41-45`)
  reads with `entity.model_validate(row, from_attributes=True)` and writes with `self._row(**entity.model_dump())`.
  A nested model on an entity therefore reaches the JSON column through its own serialiser. A dict read from the
  column reaches the nested model through its own validator. No adapter needs to change for a field's type to
  change, as long as the model dumps to the dict that is stored today.
- **Two JSON columns hold the dicts in question.** `mcp_servers.capabilities` (`rows/mcp_server_row.py:53`, server
  default `'{}'`) and `upstream_oauth_clients.metadata` (`rows/upstream_oauth_client_row.py:28`). Both stay `JSON`
  columns typed `dict` on the row class. The rows are storage, and ADR-0034 keeps their shape apart from the entity.
- **Published API surface is untouched.** `ServerRead.capabilities: dict` (`schemas/servers/server_read.py:41`) and
  `ServerJsonImport.document: dict[str, Any]` (`schemas/servers/server_json_import.py:9`) stay as they are, so
  `apps/web/openapi.json` does not change.

## Goals / Non-Goals

**Goals:**

- No layer hands another a tuple or an untyped dict for the five values named in the proposal.
- Every JSON value stored before this change loads after it and means the same thing. Every value written after it
  is readable by the code before it, so a rollback needs no data step.
- Each part merges alone, behind its own characterisation tests, with the suite green after every task.

**Non-Goals:**

- Typing the client-side capability dicts (`SessionRecord.client_capabilities`) or the inspector's pass-through
  `capabilities`. Neither is walked by domain logic.
- Changing what the management API accepts or returns, including validation messages for runtime config keys.
- A data migration that rewrites stored rows into a new shape.

## Decisions

### `PageSlice[T]`: a generic model in the persistence contracts

`PageSlice[T]` (application, `application/contracts/persistence/page_slice.py`) is a `BaseModel` with `items: list[T]`
and `total: int`. Every one of the 23 `tuple[int, list[T]]` signatures returns it. They are:

- seven contract signatures (`repository.py`, `user_`, `api_key_`, `audit_`, `tool_`, `bundle_prompt_` and
  `bundle_resource_repository.py`)
- `SqlAlchemyRepository.page` and nine Postgres adapters
- five in the in-memory fakes

`Page.of` (`schemas/common/page.py:15`) takes a `PageSlice` in place of `rows, total`. Callers that only want the rows
read `.items` (`config_export_service.py:66-68`, `endpoint_service.py:70,99`, `discovery_service.py:233`).

- It lives in `contracts/`, not `schemas/`, because it is the repositories' return type, not an API DTO. `Page` stays
  the published envelope.
- Its items are entities, which are already validated models. Pydantic does not revalidate model instances by
  default, so building a slice costs a list copy.
- *Alternative:* return `Page[T]` itself from repositories. Rejected: `Page` carries `offset` and `limit`, which the
  caller already holds, and it is an API schema. A repository naming a `schemas/` type would turn the dependency
  direction inside out.
- *Alternative:* a `NamedTuple`. Rejected: it is still a tuple, unpacks positionally, and the rule is Pydantic
  everywhere.

### `RuntimeSettings`: one typed field per key, and the registry derived from it

`RuntimeSettings` (domain, `domain/config/runtime_settings.py`) is a frozen model. It has one field per key now in
`DEFAULTS` (`domain/config/config_registry.py:46-75`). Each field carries its type, default, `ge`/`le` bounds and a
`description` (the comment that sits above the key today). `DEFAULTS` is built from `RuntimeSettings.model_fields`:
`value_type` comes from the annotation, `minimum` and `maximum` from the field's `Ge`/`Le` metadata. A key is then
declared once.

`ConfigSetting.coerce` and the module-level `coerce` stay as they are, so the management API's 422 messages
(`"max_request_bytes must be at least 65536"`) do not change.

`RuntimeConfig` (`application/serving/runtime_config.py`) changes as follows:

- `_cache` and `_snapshot` become `RuntimeSettings`, built once per load: `RuntimeSettings(**coerced_overrides)`.
  Defaults fill the rest, as `dict.get(key, default)` does now.
- `snapshot` (property, no I/O) replaces `current(key)`. Before the first load it is `RuntimeSettings()`, the
  registry defaults, as today.
- `async settings()` replaces `get(key)`. It keeps the `cache_disabled` flush and the lazy load.
- `session_lifetime()`, `call_timeouts()` and `token_policy()` read from `settings()`. Their `int(...)` and
  `float(...)` casts go, because the fields are already typed.
- `all()` is removed. Nothing calls it: `ConfigService.list` builds its own view from the rows.

The callers become `(await runtime_config.settings()).server_error_attempts` (`upstream_health.py:47`,
`audit_purger.py:47`, `cache_hints.py:21`) and `runtime_config.snapshot.max_request_bytes` (`providers.py:57`,
`composition_root.py:190,260-262`). `providers.py:56` reads `RuntimeSettings().max_request_bytes` before the container
exists.

- *Alternative:* keep `DEFAULTS` literal and add a parity test against a hand-written `RuntimeSettings`. Rejected:
  the key would still be declared twice. The test would catch drift, but deriving one from the other makes drift
  impossible.
- *Alternative:* validate stored values through `RuntimeSettings` itself instead of `ConfigSetting.coerce`.
  Rejected: Pydantic's messages differ from today's, and those messages are what an operator sees on a 422.
- *Alternative:* per-key async accessors only (`call_timeouts()`-style for all 15 keys). Rejected: fifteen methods
  where one typed snapshot does, and the no-I/O callers need a synchronous form anyway.

### `server.json`: lenient models that skip what the code skips today

`RegistryServerDocument`, `RegistryRemote` and `RegistryHeader` live in the application layer, one class per file
under `application/management/server_json/`. They describe a third-party document the importer reads. They are not
an API DTO, so they stay out of `schemas/` and out of OpenAPI. All three use `extra="ignore"` and match today's
leniency:

| Today (`server_json_importer.py`) | Model |
|---|---|
| `document.get("remotes") or []`, non-dict items dropped (line 23) | `remotes: list[RegistryRemote]`, default `[]`; a wrap validator reads a value that is not a list as empty and drops items that are not objects |
| `r.get("type")`, shown with `str(...)` in the problem (line 28) | `type: str \| None`; the problem text uses `str(remote.type)`, so a missing type still reads `None` |
| `r.get("url")` truthy for a usable remote (line 24) | `url: str \| None`; `RegistryRemote.is_usable` is `type == "streamable-http" and bool(url)` |
| `remote.get("headers") or []`; headers that are not objects or have no `name` dropped (lines 48-49) | `headers: list[RegistryHeader]` through the same wrap validator; `name: str \| None`, and the importer keeps named ones |
| `bool(header.get("isRequired", False))` (line 44) | `is_required: bool` with alias `isRequired`, and a `BeforeValidator(bool)` so Python truthiness is kept |
| `document.get("name")`, `"description"`, `"websiteUrl"` | `name`, `description`, `website_url` (alias `websiteUrl`), all `str \| None` |

`ServerJsonImporter.draft(document: dict[str, Any])` keeps its signature. It validates once into
`RegistryServerDocument` and drafts from typed fields. The problems and URL-variable logic move unchanged, and the
first usable remote is `next((r for r in doc.remotes if r.is_usable), None)`.

- *Alternative:* type the DTO as `document: RegistryServerDocument`. Rejected: it publishes a third-party schema as
  the gateway's API surface, changes `openapi.json` and the generated TS types, and moves validation failures from
  the importer to FastAPI.

### `ServerCapabilities`: typed members, every other key kept, the same snapshot out

`ServerCapabilities` (domain, `domain/servers/server_capabilities.py`) is a frozen model with `extra="allow"` and
these members:

- `tools: ListChangedCapability | None`
- `prompts: ListChangedCapability | None`
- `resources: ResourcesCapability | None`
- `completions: OpenCapability | None`
- `logging: OpenCapability | None`

The helper models sit one per file beside it. `ListChangedCapability` has `list_changed: bool | None` (alias
`listChanged`). `ResourcesCapability` adds `subscribe: bool | None`. `OpenCapability` is an empty marker. All three
also keep extra keys. A member is `None` exactly when its key was absent. That keeps the rule in the field's
description, "a key is present exactly when that capability was advertised", and `{}` reads as advertised.

- **Serialisation is the snapshot.** A wrap `model_serializer` dumps by alias, leaves out the `None` members and
  keeps the extra keys. `ServerCapabilities.model_validate(raw).model_dump() == raw` therefore holds for every
  snapshot the probe writes. The probe dumps the SDK object with `exclude_none=True`
  (`infrastructure/fastmcp/upstream_probe.py:81-85`), so a stored snapshot never holds an explicit `null`. The
  generic row mapping, `_plain` in the import report and `ServerRead` all see today's dict.
  `ServerRead.from_entity` (`server_read.py:88`) sets `data["capabilities"] = server.capabilities.model_dump()`,
  because `ServerRead.capabilities: dict` does not accept a model instance.
- **Entity behaviour moves onto it.**
  - `advertises(ServerCapability)`
  - `accepts_resource_subscriptions`
  - `tools_list_changed`, `prompts_list_changed` and `resources_list_changed`

  `McpServer.advertises` and `accepts_resource_subscriptions` delegate to them. `_listen_filter`
  (`pooled_upstream_sessions.py:400`) reads the three list-changed properties instead of probing dicts.
- **Aggregation is a fold.** `ServerCapabilities.union(other)` keeps every member present on either side. A
  `listChanged` or `subscribe` flag is `True` if either side says `True`, and absent otherwise. Extra keys are not
  carried into a union, because the bundle advertises none of them today.
  `ServerCapabilities.relayable(notifications: bool)` returns what the gateway can re-advertise from a member:
  - `prompts`, `resources`, `completions` and `logging` when present, never `tools`
  - their flags only when `notifications` is true

  `aggregate_capabilities` (`domain/bundles/bundle_capabilities.py`) then reads:

  ```python
  own = ServerCapabilities.of_bundle_content(view)  # prompts/resources with listChanged, completions
  members = (s.capabilities.relayable(member_notifications) for s in view.servers.values())
  return reduce(ServerCapabilities.union, members, own).with_tools_list_changed()
  ```

  It returns `ServerCapabilities`. `initialize_handler.py:51` and `server_discover_handler.py:27` put
  `.model_dump()` into the result. The wire object is unchanged: `{"tools": {"listChanged": true}, ...}`, and a
  member-only prompt source without relayed notifications is `"prompts": {}`.
- **The probe builds it.** `ProbeResult.capabilities` (`contracts/upstream/upstream_probe.py:17`) becomes
  `ServerCapabilities | None`. `FastMcpUpstreamProbe` validates the SDK object's JSON dump into it.
  `DiscoveryService` (`discovery_service.py:170-171`) assigns it unchanged.
- *Alternative:* reuse the MCP SDK's `mcp.types.ServerCapabilities`. Rejected: `domain/` and `application/` may not
  import `mcp` (import-linter "driver-free" contract), and the SDK type moves with the SDK.
- *Alternative:* keep the dict and add typed read-only properties. Rejected: the fold still has to rebuild dicts, and
  `ProbeResult` would keep carrying an untyped value across the layer.
- *Naming:* the singular `ServerCapability` enum already exists for one capability key. The plural is the object the
  MCP spec calls `ServerCapabilities`. Infrastructure that needs both imports the SDK's through its module
  (`mcp.types`).

### `UpstreamClientMetadata`: one value object, the same flat JSON

`UpstreamClientMetadata` (domain, `domain/upstream_oauth/upstream_client_metadata.py`) is frozen and has:

- `identification: ClientIdentification` (default `PREREGISTERED`)
- `grant: UpstreamGrant` (stored key `grant_type`, default `AUTHORIZATION_CODE`)
- `step_up_scopes: tuple[str, ...]`
- `endpoints: UpstreamMetadata | None`

The defaults are today's `.get(..., default)` fallbacks (`upstream_client_config.py:33,38,47`), so a record without
a key means what it means today. Notably, a pre-identification record written by `meta.model_dump(exclude_none=True)`
still reads as admin-stored, as it does now.

- **Stored shape.** The column holds a flat object: the `UpstreamMetadata` fields beside the three gateway keys. A
  `model_validator(mode="before")` splits a flat dict. `endpoints` is built from it when both `authorization_endpoint`
  and `token_endpoint` are truthy. That is the condition `upstream_connect_flow.py:49` uses today; otherwise
  `endpoints` is `None`. A wrap `model_serializer` writes the flat shape back:
  - the endpoint fields with `exclude_none` and without `step_up_scopes`, as `save_registration` writes now
  - `identification` and `grant_type` always
  - `step_up_scopes` only when non-empty

  Unknown keys are ignored. The code before this change reads every key written after it.
- **Behaviour moves onto it.** Each replaces a block of string-key edits:
  - `UpstreamClientMetadata.obtained(meta, identification)` replaces `upstream_token_storage.py:159-162`.
  - `configured_by_admin(grant, authorization_url, token_url)` replaces `upstream_oauth_config_service.py:67-74`.
    It keeps the remembered endpoints and replaces only the two URLs when both are given.
  - `with_step_up(scopes)` replaces `upstream_token_storage.py:190-196`. It merges in order without duplicates, and
    the caller compares old and new to learn whether anything was added.
  - `remembered_endpoints` replaces `upstream_connect_flow.py:48-51`. It is `endpoints` with `step_up_scopes` set, or
    `None`.
  - `is_admin_stored` is `identification == PREREGISTERED`.
- **The client config carries it.** `UpstreamClientConfig.metadata` (`upstream_client_config.py:23`) becomes
  `UpstreamClientMetadata`. Its `identification`, `grant`, `issuer`, `step_up_scopes` and `is_admin_stored`
  properties read typed fields. `UpstreamOAuthConfigService.status` (`upstream_oauth_config_service.py:84-97`) and
  `ConfigExportService._client` (`config_export_service.py:101-121`) build their DTOs from typed fields, and
  `ServerService._ensure_grant_allows_identity` (`server_service.py:83`) compares `client.metadata_.grant`.
- **The constants go.** `IDENTIFICATION_KEY`, `GRANT_KEY` and `STEP_UP_KEY` are deleted, and the key names live only
  in the model's aliases.
- **The field keeps its name.** `metadata_` stays as named, because SQLModel reserves `metadata` on the row and the
  generic mapping pairs fields by name.
- *Alternative:* store a nested `{"endpoints": {...}, "identification": ...}` object. Rejected: it needs a data
  migration, and a rollback would misread every row written after it.
- *Alternative:* flatten every `UpstreamMetadata` field into `UpstreamClientMetadata`. Rejected: it duplicates eleven
  field declarations and their descriptions, and drifts when `UpstreamMetadata` gains one.

### Order and independence

The five parts share no code. The tasks put them in rising order of risk, each a group that can merge alone:

1. pages (mechanical)
2. runtime settings
3. `server.json`
4. capabilities
5. client metadata (the only stored data with history)

Each group writes its characterisation tests first, on the old code, then refactors under them.

## Risks / Trade-offs

- [A stored capabilities snapshot holding an explicit `null` member (`{"prompts": null}`) is read as "not
  advertised", where `"prompts" in caps` read it as advertised.] → The probe has always dumped with
  `exclude_none=True`, and the migration's server default is `'{}'`, so no stored row can hold one. A test asserts
  the probe output never contains `null`.
- [The serialised snapshot differs from the stored one in key order, or by a dropped extra key, and the import
  report starts showing upstreams as "changed".] → The report compares two dumps made by the same code, so order
  cannot differ between them. A round-trip test runs over every capabilities fixture in the suite plus an SDK
  `ServerCapabilities` with `experimental` and extension keys.
- [A client metadata record holds discovery keys without both endpoints, and they are dropped on its next write.] →
  No code path writes such a record. `save_registration` dumps a full `UpstreamMetadata`, whose two endpoints are
  required, and the admin path writes both or neither. A characterisation test pins every shape the code has written.
- [An invalid enum value in stored metadata (`identification: "bogus"`) now fails when the row loads, where it
  failed when a property was first read.] → Both values were only ever written from the enums. Failing at load is
  earlier, not new.
- [`RuntimeSettings` derived bounds disagree with today's `DEFAULTS`.] → Task 2.1 pins today's registry as a
  literal table before the refactor and asserts the derived registry equals it.
- [Parallel changes for S8 and S11 also edit `pooled_upstream_sessions.py`.] → This change touches only
  `_listen_filter`, a 15-line static method. Whichever change merges second rebases.

## Migration Plan

None. No schema or data migration: both JSON columns keep their shape, and the code before this change reads
everything written after it. A rollback is a plain revert of the code.

## Open Questions

- **`server.json` documents that violate the schema's own types.** One example is `"url": 5` on a remote, or
  `"description": 7` on a header. Today the result is accidental: a mismatch in the first usable remote or at the top
  level ends in a 500 (`TypeError` or a `ServerJsonDraft` validation error), and one elsewhere is ignored. The design
  above keeps the 500 at the top level (the `ValidationError` propagates as the `AttributeError` does now). It skips
  a mistyped entry inside `remotes` or `headers` like a non-object, so a few 500s become drafts with a problem
  listed. Two choices remain open, and either keeps the task breakdown as it is:
  - accept that as part of the refactor, since UPS-15 is silent on malformed documents
  - also turn the remaining top-level 500 into a 422 (`InvalidInputError`), which is an observable change and would
    get its own UPS-15 scenario in a follow-up change

## Adjustments made during implementation

Each of these keeps the goals above. They are recorded here because the code differs from the decisions as written.

- **`PageSlice` is imported by module path.** `application/contracts/persistence/__init__.py` exports nothing, and
  every contract is imported from its own module, so the slice is too.
- **`KIB` and `MIB` live in `runtime_settings.py`.** The byte bounds are declared there, and the registry no longer
  needs them. The tests that imported them from `config_registry` import them from their owner.
- **The `UnknownConfigKey` check moved off `RuntimeConfig`.** With no string-keyed read left, an unknown key can only
  reach `coerce`, which still raises it. `test_defaults_served` asserts that there, and compares the loaded settings
  with `RuntimeSettings()` as a whole.
- **`server.json`: the shared validator has its own module.** `valid_entries.py` beside the three models builds the
  `BeforeValidator` for a list of entries. `isSecret` follows Python truthiness like `isRequired`, as it did.
  `RegistryServerDocument.first_usable_remote` replaces the `next(...)` in the importer. The open question was settled
  with the first choice. `test_ups15_a_mistyped_entry_is_skipped_like_a_non_object` pins it: an entry with mistyped
  keys is skipped, and a mistyped top-level key still fails. `ServerJsonImporter.draft` drops from C (17) to B (10).
- **Capabilities: a shared `CapabilityObject` base.** The serialiser described above also keeps key order. The base
  class records the wire keys in the order they were read, and dumps them in that order. A snapshot therefore comes
  back from `GET /api/v1/upstreams/{name}` and from the JSON column with its keys in the order stored, not only as an
  equal dict. Equality compares the dumps, so key order never makes two snapshots unequal.
- **`of_bundle_content` takes three booleans, not the `BundleView`.** `domain/bundles/bundle_view.py` imports
  `McpServer`, which imports `ServerCapabilities`, so the capabilities module cannot import the view.
- **The existing PROT-11 and BND-27 aggregation tests gained `.model_dump()`.** `aggregate_capabilities` now returns
  a model, so those tests read its wire form. Their expected dicts are unchanged, and `aggregate_capabilities` drops
  from D (23) to A (3).
- **Client metadata: the gateway keys are written when present, not always.** Writing `identification` and
  `grant_type` on every record would have added keys to gateway records and to the `{}` that `forget_registration`
  leaves, so stored JSON would change. The serialiser writes a gateway key exactly when the record holds it: read from
  storage, or set by `obtained`, `configured_by_admin` or `with_step_up`. Defaults still apply on read. The endpoints
  dump with `exclude_unset`, so an admin record keeps its two keys.
- **Client metadata: unknown keys are kept.** The admin and step-up paths copied the whole dict before, so an unknown
  key survived them. The model keeps such keys (`extra="allow"`). This includes endpoint keys of a record that lacks
  one of the two required endpoints. `obtained` still starts a fresh record, as `save_registration` did.
  `configured_by_admin` edits the stored form and validates it again, so it edits exactly the keys the dict code
  edited.
- **Key order of the client metadata record.** The record is written in a fixed order: endpoints, `identification`,
  `grant_type`, `step_up_scopes`, then unknown keys. Every record written back is equal, as a dict, to what the dict
  code wrote. Registrations, new admin clients and step-up scopes on a registration keep their key order. Two cases
  reorder keys. An admin client stored over a record that already holds `step_up_scopes` puts `grant_type` before it,
  where the dict code appended it. A record with an unknown key keeps that key last. Nothing reads this column's key
  order.
- **`issuer` is read from the endpoints.** A record whose endpoints are incomplete reports no issuer. Before, it
  reported a lone `issuer` key. No code path writes such a record (see Risks).
- **More write-path characterisation.** `test_upstream_client_metadata_rows.py` also pins the stored JSON that each
  write path leaves behind: a registration, step-up scopes, and an admin client over each shape. These tests were
  written against the dict code first.
