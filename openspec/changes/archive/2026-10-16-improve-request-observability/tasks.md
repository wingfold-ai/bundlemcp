# Tasks

## 1. Log stream and request context (OPS-8, DEP-2)

- [x] 1.1 Apply the maintainers' log-stream decision (proposal "Open decision"): keep stderr, or pass `sys.stdout` to
      the handler in `configure_logging`; correct the module and function docstrings to the chosen stream and verify
      `test_ops8_logs_written_to_stderr` captures a line on that stream only
- [x] 1.2 Add the pure ASGI request-context middleware in `api/http/` (clear, `request_id`, `client_ip` via
  `client_ip()`, `X-Request-Id` response header, one `http.request` line, clear in `finally`) and register it in
  `main/app.py`; verify `test_ops8_request_id_returned_and_logged` and `test_dep2_logs_carry_derived_client_ip`
- [x] 1.3 Silence uvicorn's access logger in `configure_logging` and verify
  `test_ops8_one_access_line_per_request`
- [x] 1.4 Add the closed-set `bind_request_fields` helper and bind endpoint and caller in `AdmissionGate.admit_caller`,
  session id in `SessionMcpAdapter`, server and tool in the tool-call pipeline, caller in `ManagementAuth`; verify
  `test_ops8_tool_call_lines_carry_request_context` (and that no key value appears) and
  `test_ops8_rejected_before_auth_has_no_caller`
- [x] 1.5 Verify `test_ops8_context_does_not_leak_between_concurrent_requests` with two concurrent requests on
  different endpoints
- [x] 1.6 Document the context fields and `X-Request-Id` in `docs/self-hosting/operations.md` (log fields table) and
  `docs/self-hosting/troubleshooting.md` (find a request by id); verify `python3 tools/check_docs_links.py`

## 2. Readiness (OPS-10, DEP-4)

- [x] 2.1 Add the `ReadinessReport` model and make the probe check Postgres, Valkey and schema currency separately,
  catching driver errors per check; verify `test_ops10_postgres_down_is_503`, `test_ops10_valkey_down_is_503` and
  `test_ops10_report_names_failing_check`
- [x] 2.2 Compute the shipped migration head at startup and compare with `alembic_version` (behind → not ready; at or
      past → ready); verify `test_dep4_readyz_false_until_schema_current` on sqlite with a stamped older revision
- [x] 2.3 Return 200/503 with the report from `HealthController.readyz`; update the `ReadinessProbe` contract docstring
  and `docs/self-hosting/deploy.md` (health checks, one-shot migration jobs) and verify
  `python3 tools/check_docs_symbols.py`

## 3. Optional tracing (OPS-12)

- [x] 3.1 Add the `otel` optional extra to `packages/bundlemcp/pyproject.toml` (`>=` pins) and verify
  `uv sync --all-packages --extra otel` succeeds
- [x] 3.2 Add the `CallTracer` contract and the no-op tracer, and wrap the upstream call in the tool-call pipeline;
      verify `uv run lint-imports` and `test_ops12_tracing_is_requested_only_by_an_exporter_endpoint`
- [x] 3.3 Add `infrastructure/opentelemetry/tracing.py` (SDK from `OTEL_*`, FastAPI/SQLAlchemy/redis instrumentation,
  upstream-call span) loaded by `main/` only when an exporter endpoint is configured; verify
  `test_ops12_off_loads_no_tracing_code` (`sys.modules`) and `test_ops12_upstream_call_span_attributes` with an
  in-memory span exporter
- [x] 3.4 Verify `test_ops12_spans_carry_no_secrets` (key value, forwarded header value, arguments absent) and
  `test_ops12_missing_extra_warns_once`
- [x] 3.5 Document tracing (variables, extra, image build arg) in `docs/self-hosting/configuration.md` and
  `operations.md`; verify `python3 tools/check_docs_settings.py`

## 4. Overhead report (OPS-13)

- [x] 4.1 Make the echo upstream reachable from the integration runner (published port or in-network runner) and verify
  a direct `tools/call` against it from the test host succeeds
- [x] 4.2 Add `tests/integration/test_overhead_budget.py` (warm-up, 200 sequential calls each path, p50/p95, JSON
      report, no budget assertion) and verify `BUNDLEMCP_INTEGRATION=1 uv run pytest tests/integration -k ops13` prints
      the table
- [x] 4.3 Upload the report as a CI artifact and append it to the job summary in `.github/workflows/ci.yml`; verify the
  workflow passes `actionlint` or a dry run

## 5. Architecture records

- [x] 5.1 Write the ADR (request context, readiness report, optional tracing) as the next free number in `docs/adr/`,
  index it and reference it from arc42 §8; verify `python3 tools/check_adr_graph.py`
- [x] 5.2 Add the optional OTLP collector to `docs/likec4/` and verify `npx likec4 validate docs/likec4`

## 6. Gates

- [x] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` and verify all
  pass
- [x] 6.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`,
  `check_adr_graph.py` and verify all pass
- [x] 6.3 Run `cd apps/web && npm run openapi` and verify the generated files are unchanged (health routes are not in
      the schema) or commit them
- [x] 6.4 Run `openspec validate --all --strict` and verify it passes
