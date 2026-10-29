# Tasks

## 1. Public-only egress scope (AUTH-13)

- [x] 1.1 Add `EgressScope` (`UPSTREAM`, `PUBLIC`) to `infrastructure/egress/`, give `judge_address`,
  `check_url_allowed`, `GuardedNetworkBackend` and `guarded_client` a `scope` defaulting to `UPSTREAM`, and refuse
  non-global addresses under `PUBLIC` unless allow-listed. Verify with infrastructure tests
  `test_auth13_public_scope_refuses_private_ranges` (10/8, 172.16/12, 192.168/16, 100.64/10, fc00::/7, 64:ff9b::/96,
  2002::/16 with an embedded private or link-local IPv4, documentation ranges),
  `test_auth13_public_scope_honours_allow_cidrs`, a rebinding test under `PUBLIC`,
  and the existing SEC-2 tests unchanged under `UPSTREAM`
- [x] 1.2 Write ADR-0060 "Unauthenticated fetches use a public-only egress scope" (extends ADR-0048), list
  it in `docs/adr/README.md`, update arc42 §8 (egress), and verify with `python3 tools/check_adr_graph.py` and
  `python3 tools/check_docs_links.py`

## 2. Bounded, failure-cached fetch (AUTH-13)

- [x] 2.1 Fetch metadata documents with `scope=PUBLIC`, a streamed body capped at 16 KiB, a 5-second overall deadline
      and a two-step parse (`json.loads`, then `model_validate`). Verify with
      `tests/infrastructure/test_client_metadata_fetcher.py`: `test_auth13_private_address_not_fetched`,
      `test_auth13_oversized_document_refused`, `test_auth13_slow_document_cut_off` (a mock transport streaming slowly),
      and the existing fetcher tests
- [x] 2.2 Add the 60-second negative cache (`bmcp:cimd:fail:{digest}`, a `CachedFetchFailure` model). Verify with
      `test_auth13_failed_fetch_not_repeated` (the mock transport counts one request) and
      `test_auth13_cached_failure_keeps_its_kind` (invalid stays invalid, unreachable stays unreachable)
- [x] 2.3 Verify the authorize endpoint end to end in `tests/api/test_oauth.py` with
  `test_auth13_authorize_refuses_private_metadata_url`, and document the caps in `docs/integrate/http-surface.md`

## 3. Switch to turn metadata-document clients off (AUTH-34)

- [x] 3.1 Add `Settings.client_metadata_documents_enabled` (described for operators), register
      `MetadataDocumentClientSource` only when it is on, and set `client_id_metadata_document_supported` from it. Verify
      with `test_auth34_off_refuses_without_fetch`, `test_auth34_off_advertised_in_metadata` and
      `test_auth34_default_on`
- [x] 3.2 Document `BUNDLEMCP_CLIENT_METADATA_DOCUMENTS_ENABLED` in `docs/self-hosting/configuration.md`, run
  `cd apps/web && npm run openapi` and confirm no drift, and verify with `python3 tools/check_docs_settings.py`

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`; all pass
