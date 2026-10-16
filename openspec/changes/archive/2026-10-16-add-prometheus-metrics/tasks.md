# Tasks

## 1. Metrics contract and adapter

- [x] 1.1 Add `prometheus-client` (`>=` pin, latest stable) to `packages/bundlemcp/pyproject.toml` and verify
  `uv sync --all-packages` succeeds
- [x] 1.2 Add the `GatewayMetrics` protocol and its label enums in `application/contracts/observability/` and verify
  `uv run lint-imports` passes
- [x] 1.3 Implement the Prometheus adapter over a private registry and the memory fake; verify with
  `tests/infrastructure/` tests (`test_ops9_*`) that each method produces the documented metric name and labels
- [x] 1.4 Add `BUNDLEMCP_METRICS_ENABLED` to `Settings` with a described `Field` and verify
  `python3 tools/check_docs_settings.py` passes after documenting it in `docs/self-hosting/configuration.md`

## 2. Record into the contract

- [x] 2.1 Move the rate-limit gate and `ValkeyRateLimiter` to `GatewayMetrics` (`rate_limit_rejected`,
  `traffic_limiter_failed_open`) and verify `test_ep18_rejection_counted_in_metrics` and
  `test_ep21_the_two_limiters_fail_open_on_separate_alarms`
- [x] 2.2 Give `ValkeyAuthFailureLimiter` its own fail-open alarm (`auth_limiter_failed_open`) plus a WARN log, and
  record `auth_failed` / `auth_locked_out`; verify `test_ep21_auth_limiter_fail_open_has_own_alarm` and
  `test_sec9_lockout_visible_in_metrics`
- [x] 2.3 Record tool-call count and duration, metering denies and upstream in-flight/failure in the tool-call pipeline;
  verify `test_ops9_tool_call_counted_and_timed` and `test_ops9_metering_deny_counted`
- [x] 2.4 Delete `Counters`, its constants and `InProcessCounters`; delete `.import_linter_cache` and verify
  `uv run lint-imports` and `uv run pytest -q` pass with no remaining reference
- [x] 2.5 Correct the docstrings of `audit_writer.py` (`dropped`) and anything else that described the old sink, and
  verify `python3 tools/check_docs_symbols.py` passes

## 3. Gauges and the `/metrics` route

- [x] 3.1 Register scrape-time gauges for active sessions (stream registry), audit queue depth and per-store health
  (with timeout and 5 s cache); verify `test_ops9_store_health_gauge` with fakeredis made unreachable
- [x] 3.2 Add `MetricsController` under `api/metrics/controllers/` behind `ManagementAuth`, excluded from the schema,
  mounted in `main/app.py` only when enabled; verify `test_ops9_metrics_requires_service_key` (401 / 403 / 200) and
  `test_ops9_metrics_disabled_is_404`
- [x] 3.3 Add `test_ops9_replicas_export_their_own_counters` (two apps, one shared fake Valkey) and verify a call served
  by one app increments only that app's counter
- [x] 3.4 Update `docs/self-hosting/operations.md` and `requirements.md` (metrics exist; per-replica scrape config
  example with bearer auth; example alerts for fail-open and degraded listings) and verify
  `python3 tools/check_docs_links.py` passes

## 4. Degraded `tools/list` (OPS-11)

- [x] 4.1 Count and WARN-log each `error`-health member in `ToolsListHandler` and verify
  `test_ops11_unhealthy_member_marks_listing_degraded` and `test_ops11_healthy_listing_not_degraded`
- [x] 4.2 Note the metric in `docs/manage/servers.md` (health) and verify the docs build links resolve

## 5. Secrets stay out of metrics (SEC-10)

- [x] 5.1 Add the redaction test helper (`assert_redacted(text, secrets)`) in `packages/bundlemcp/tests/redaction.py`
  and verify `test_sec10_metrics_labels_carry_no_secrets` (API key, bearer, forwarded header, `sub`, key id)
- [x] 5.2 Apply the helper to captured logs and error bodies of a rejected bad key and verify
  `test_sec10_redaction_logs_and_error_bodies`

## 6. Architecture records

- [x] 6.1 Write the ADR for the export model (per-replica scrape, management auth, typed contract, closed labels) as the
  next free number in `docs/adr/`, add it to `docs/adr/README.md` and arc42 §8/§9, and verify
  `python3 tools/check_adr_graph.py` passes
- [x] 6.2 Add `/metrics` and the Prometheus scraper to `docs/likec4/` and verify `npx likec4 validate docs/likec4`

## 7. Gates

- [x] 7.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` and verify all
  pass
- [x] 7.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`,
  `check_adr_graph.py` and verify all pass
- [x] 7.3 Run `cd apps/web && npm run openapi` and verify `openapi.json` and `types/api.d.ts` are unchanged (the route
  is excluded from the schema)
- [x] 7.4 Run `openspec validate --all --strict` and verify it passes
