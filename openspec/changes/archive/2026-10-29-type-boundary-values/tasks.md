# Tasks

Groups 1 to 5 are independent and can each merge as their own pull request, in any order. Each group writes its
characterisation tests against the code as it is, sees them pass, and only then changes the code under them.

## 1. Typed pages

- [x] 1.1 Add `PageSlice[T]` (`items: list[T]`, `total: int`, both described) in
  `application/contracts/persistence/page_slice.py` and export it from the package. Verify with
  `test_mgmt5_a_page_slice_keeps_entities_unrevalidated` in `tests/application/`, which builds a slice of entities
  and asserts the same instances come back
- [x] 1.2 Return `PageSlice[...]` from `SqlAlchemyRepository.page`, every Postgres adapter, every in-memory fake and
  the seven contract signatures (the 23 `tuple[int, list[...]]` sites). Change `Page.of` to take a `PageSlice`, and
  update every caller: the paging services, `config_export_service.py:66-68`, `endpoint_service.py:70,99`,
  `discovery_service.py:233` and `tests/infrastructure/test_audit_retention.py:40`. Verify that
  `grep -rn "tuple\[int, list" packages/bundlemcp` finds nothing, and that the existing MGMT-5 tests
  (`tests/api/test_api.py`, `tests/api/test_audit_api.py`) and `uv run lint-imports` pass

## 2. Typed runtime settings

- [x] 2.1 Characterise first: add `test_ses18_the_registry_keys_defaults_and_bounds` in
  `tests/domain/test_runtime_settings.py`. It pins today's `DEFAULTS` as a literal table of key, type, default,
  minimum and maximum. Add `test_ses18_rejected_values_keep_their_messages` beside it, which pins the
  `coerce` messages for a wrong type, a value below the minimum and one above the maximum
  (`"max_request_bytes must be at least 65536"`). Both pass on the current code
- [x] 2.2 Add the frozen `RuntimeSettings` in `domain/config/runtime_settings.py`, one described field per key with
  its `ge`/`le` bounds, and build `DEFAULTS` from its `model_fields`, keeping `ConfigSetting.coerce` and its messages.
  Verify that both 2.1 tests still pass
- [x] 2.3 Replace `RuntimeConfig.current(key)` with the `snapshot` property and `get(key)` with `async settings()`,
  both returning `RuntimeSettings`. Remove the unused `all()`, drop the casts in `session_lifetime`, `call_timeouts`
  and `token_policy`, and move the callers to typed fields:
  - `providers.py:56-57`
  - `composition_root.py:190,260-262`
  - `upstream_health.py:47`
  - `audit_purger.py:47`
  - `cache_hints.py:21`

  Update `tests/application/test_runtime_config_snapshot.py`, `tests/api/test_request_body_limit.py:113` and
  `tests/api/test_config_cache_switch.py:23-25` to the typed form, and verify that the SEC-7 snapshot tests still
  show no unit of work opened by `snapshot`. Confirm with `grep -rn "\.current(\"" packages/bundlemcp` that no
  string-keyed read remains
- [x] 2.4 Change `RuntimeConfig.current` to `RuntimeConfig.snapshot` in `.claude/docs/design-principles.md`, and
  verify with `python3 tools/check_docs_symbols.py`

## 3. Lenient `server.json` models

- [x] 3.1 Characterise first in `tests/application/test_server_setup_on_fakes.py`. Each test passes on the current
  importer:
  - `test_ups15_unknown_keys_and_non_object_entries_are_ignored` (a non-object remote, a non-object header, a
    header without a name, unknown keys at every level, `remotes` given as a string)
  - `test_ups15_a_remote_without_a_type_is_reported_by_name` (asserts the `found: None` problem text)
  - `test_ups15_is_required_follows_truthiness` (`"isRequired": "yes"` and `1` read as required)
- [x] 3.2 Add `RegistryServerDocument`, `RegistryRemote` and `RegistryHeader` in `application/management/server_json/`,
  one class per file, `extra="ignore"`, every field described, with the shared wrap validator that drops non-object
  entries and reads a non-list as empty. Rewrite `ServerJsonImporter.draft` to validate once and draft from typed
  fields. Verify that 3.1, `test_ups15_a_server_json_draft_carries_the_declared_headers` and
  `test_ups15_a_server_json_becomes_a_draft` pass unchanged, and that `apps/web/openapi.json` is unchanged after
  `cd apps/web && npm run openapi`

## 4. Typed capabilities

- [x] 4.1 Characterise first: add `test_prot11_aggregation_matrix` to `tests/domain/test_bundle_capabilities.py`. It is
  table-driven over members with and without `listChanged`/`subscribe`, `completions`, `logging` and an
  `experimental` key, over own prompts and resources, and over relayed notifications on and off, and it asserts the
  exact wire dicts the current `aggregate_capabilities` returns. Add `test_ups22_the_snapshot_is_returned_verbatim` in
  `tests/api/`, which stores a snapshot with an extra `experimental` key and reads it back unchanged through
  `GET /api/v1/upstreams/{name}`. Both pass on the current code
- [x] 4.2 Add the frozen `ServerCapabilities` with `ListChangedCapability`, `ResourcesCapability` and `OpenCapability`
  in `domain/servers/`, one per file. Give it the snapshot serialiser, `advertises`, `accepts_resource_subscriptions`,
  the three list-changed properties, `union`, `relayable`, `of_bundle_content` and `with_tools_list_changed`. Verify
  with `tests/domain/test_server_capabilities.py`:
  - `test_ups22_round_trip_is_identity`, over every capabilities fixture in the suite and an SDK
    `ServerCapabilities` dump with `experimental` set, built in an infrastructure test
  - `test_prot11_union_keeps_presence_and_ors_flags`
  - `test_prot11_relayable_drops_tools_and_unrelayed_flags`
- [x] 4.3 Type `McpServer.capabilities` and `ProbeResult.capabilities` with it. Delegate `McpServer.advertises` and
  `accepts_resource_subscriptions`, build it in `FastMcpUpstreamProbe`, map it in `ServerRead.from_entity`, and read
  the list-changed properties in `PooledUpstreamSessions._listen_filter`. Verify that 4.1, the existing UPS-22
  discovery tests in `tests/infrastructure/test_discovery.py` and
  `tests/infrastructure/test_pooled_upstream_sessions.py` pass, and that `test_ups22_the_probe_never_stores_null`
  in `tests/infrastructure/` asserts the probe's dump has no `None` member
- [x] 4.4 Rewrite `aggregate_capabilities` as the fold, returning `ServerCapabilities`, and dump it in
  `initialize_handler.py` and `server_discover_handler.py`. Verify that 4.1 and the four existing PROT-11 tests pass
  unchanged, and that `uv run lint-imports` passes

## 5. Typed upstream OAuth client metadata

- [x] 5.1 Characterise first: add `tests/infrastructure/test_upstream_client_metadata_rows.py`. It inserts
  `UpstreamOAuthClientRow`s on sqlite holding every shape the gateway has written, then reads each through the
  repository and `UpstreamTokenStorage.find_client_config` and asserts `identification`, `grant`, `issuer`,
  `step_up_scopes` and `is_admin_stored`. The shapes are:
  - an admin record (two endpoints, `identification`, `grant_type`)
  - a gateway record (a full `UpstreamMetadata` dump plus `identification`)
  - a record written before `identification` existed, which reads as admin-stored
  - a record with `step_up_scopes`
  - `{}` after `forget_registration`
  - a record with an unknown key

  Name the tests for UPS-25, UPS-34 and UPS-35. They pass on the current code
- [x] 5.2 Add the frozen `UpstreamClientMetadata` in `domain/upstream_oauth/upstream_client_metadata.py`, with the
  flat-shape validator and serialiser, `obtained`, `configured_by_admin`, `with_step_up`, `remembered_endpoints` and
  `is_admin_stored`. Verify with `tests/domain/test_upstream_client_metadata.py`:
  - `test_ups25_every_stored_shape_round_trips`: load, dump and load again gives an equal value, and the dump of a
    loaded record reads the same under the old `.get(...)` rules
  - `test_ups34_step_up_merges_in_order_without_duplicates`
  - `test_ups25_admin_configuration_keeps_remembered_endpoints`
- [x] 5.3 Type `UpstreamOAuthClient.metadata_` and `UpstreamClientConfig.metadata` with it, and move the callers onto
  its methods:
  - `upstream_token_storage.py:146-208`
  - `upstream_oauth_config_service.py:67-97`
  - `upstream_connect_flow.py:48-51`
  - `server_service.py:83`
  - `config_export_service.py:101-121`

  Delete `IDENTIFICATION_KEY`, `GRANT_KEY` and `STEP_UP_KEY`. Update the test that indexes the entity's dict
  (`tests/application/test_upstream_oauth_on_fakes.py:217`) to typed fields. `tests/api/test_server_setup_api.py:268`
  reads the row's JSON and stays as it is, which also pins the stored shape of `step_up_scopes`. The fixture that builds
  a client from a flat dict (`test_upstream_oauth_on_fakes.py:256`) stays as it is, since the validator accepts the
  stored shape. Verify that 5.1, 5.2 and the existing UPS-34, UPS-35 and MGMT-16 export and import tests pass, and that
  `grep -rn "metadata_\[\|metadata_ or\|\.get(\"authorization_endpoint\")" packages/bundlemcp/bundlemcp` finds nothing

## 6. Gates

- [x] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` (after
  deleting `.import_linter_cache`), `python3 tools/check_docs_links.py`, `python3 tools/check_docs_symbols.py`,
  `python3 tools/check_docs_settings.py`, `python3 tools/check_adr_graph.py`, `python3 tools/check_compose_ports.py`,
  `python3 tools/check_spec_ids.py`, `cd apps/web && npm run openapi` (which must leave `openapi.json` and
  `types/api.d.ts` unchanged, since no DTO changes) and `openspec validate --all --strict`; all pass. When a group
  merges on its own, run the same gates for it
