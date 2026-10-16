# Design: improve request observability

## Context

See [proposal.md](proposal.md) for the motivation. Today:

- `infrastructure/config/structured_logging.py::configure_logging` installs one `logging.StreamHandler()` (stderr) with
  a structlog `ProcessorFormatter`; the shared processor chain already starts with
  `structlog.contextvars.merge_contextvars`, but nothing in the codebase calls `bind_contextvars`.
- Uvicorn's access logger is routed through the same formatter; its client address is the socket peer.
- `api/http/client_ip.py::client_ip(request, settings)` implements the trusted-proxy policy and is called by the
  rate-limit gate, the auth-failure guard and client registration — not by anything that logs.
- The MCP edge resolves facts in stages (ADR-0035): `McpGatewayRouter` → `AdmissionGate.admit_caller` (endpoint +
  identity) → `StatelessMcpAdapter` / `SessionMcpAdapter` (session id). The management API resolves its caller in
  `ManagementAuth`.
- `/readyz` (`HealthController`) awaits `StoreReadinessProbe.check()`, which runs `SELECT 1` and `PING`. A Valkey
  error is mapped to 503 by `live_state_unavailable_handler`; a SQLAlchemy/asyncpg error has no handler and becomes 500.
- Migrations live in `infrastructure/postgres/migrations/` (Alembic, advisory-lock guarded in `env.py`); the image's
  `CMD` runs `alembic upgrade head` before `python main.py`.

## Goals / Non-Goals

**Goals:**

- One place that starts and clears a request's log context, and a few well-defined places that add to it.
- `/readyz` that tells the truth about stores and schema with 503s.
- Tracing that costs nothing when off.

**Non-Goals:**

- Propagating trace context (`traceparent`) to upstream MCP servers. It would add a header to every upstream request,
  which interacts with the identity-forwarding deny-list (AUTH-28); a later change can add it deliberately.
- Changing what is logged at each event, beyond the context fields.
- Making the overhead budget a CI gate.

## Decisions

### D1. A pure ASGI middleware owns the request context

`api/http/request_context_middleware.py` — a plain ASGI middleware (not `BaseHTTPMiddleware`, which runs the endpoint in
a separate task so later binds would not be visible to the middleware's own completion log). Per HTTP request it:

1. clears structlog contextvars, generates a `request_id` (UUID4 hex),
2. binds `request_id` and `client_ip` (from `client_ip()`, so DEP-2's policy is the only source),
3. adds `X-Request-Id` to the response headers,
4. writes one `http.request` access line at INFO with method, path template, status and duration,
5. clears the context in `finally`.

Uvicorn's own access logger is silenced (level raised above INFO in `configure_logging`), because its client field is
the socket peer and it would duplicate the line.

- *Alternative:* keep uvicorn's access log and add a filter that rewrites the client field. Rejected: the filter would
  need the settings and the request, which the logging layer does not have.
- *Client-supplied `X-Request-Id`* is **not** adopted: it would let a client choose the correlation id of its own lines
  (log confusion). A later change may accept it from trusted proxies only.

### D2. Bind context where each fact is resolved

| Field | Bound in | Layer |
|---|---|---|
| `endpoint` | `AdmissionGate.admit_caller`, after the endpoint lookup | `api/mcp/routing/` |
| `user_id` / `api_key_id` / `auth_method` | `AdmissionGate.admit_caller`, after authentication; `ManagementAuth` for `/api/v1` | `api/` |
| `session_id` | `SessionMcpAdapter` once the session record is loaded or created | `api/mcp/routing/adapters/` |
| `server`, `tool` | the tool-call pipeline when a tool is resolved | `api/mcp/tool_call/` |

Binding is a call to one small `api/http/log_context.py::bind_request_fields(**fields)` wrapper so the allowed keys are
a closed set (a typed model validates them) — no caller can bind a header value. `domain/` and `application/` never
bind; they log, and inherit the context.

- *Background tasks:* `asyncio.create_task` copies the current context, so the audit writer's and post-call's tasks
  started during a request inherit its id — wanted. Long-lived loops (`ToolRefresher`, `TokenPurger`) are started at
  lifespan, outside any request, and so carry no request fields.

### D3. Readiness reports per check and checks schema currency

`StoreReadinessProbe.check()` becomes `check() -> ReadinessReport` (a Pydantic model: `postgres`, `valkey`,
`migrations`, each ok or failing with a short reason). Each check catches its own driver errors, so no exception escapes
to the app. `migrations` compares the database's `alembic_version` with the script directory's head, computed once at
startup from the migrations package the library ships. `HealthController.readyz` returns 200 or 503 with the report.

- *Alternative:* a global exception handler for SQLAlchemy errors mapped to 503. Rejected for `/readyz` (it hides which
  check failed); the general Postgres-down behaviour of other routes is SES-14 in
  [complete-session-lifecycle](../archive/2026-10-16-complete-session-lifecycle/proposal.md).
- The head is read from the shipped scripts, not configured, so an image cannot be told the wrong head.

### D4. Tracing as an optional extra, loaded only when configured

`main/` checks for `OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` (and `OTEL_SDK_DISABLED` not
`true`). Only then does it import `infrastructure/opentelemetry/tracing.py`, which configures the SDK from the standard
variables and instruments FastAPI, SQLAlchemy and redis. The span per upstream call goes through a `CallTracer`
contract (`application/contracts/observability/call_tracer.py`) with a no-op implementation in
`infrastructure/memory/` used by default; the tool-call pipeline wraps the upstream call in `tracer.span(...)` with
endpoint, server, presented tool and status as attributes.

- *Zero cost:* when off, nothing from `opentelemetry` is imported (asserted by a test over `sys.modules`); the no-op
  span is a context manager that does nothing.
- httpx instrumentation is deliberately not enabled (see Non-Goals).
- *Alternative:* `opentelemetry-instrument` as the container entrypoint. Rejected: it would import and patch everything
  even when no exporter is configured, and it sits outside the composition root.

### D5. Overhead benchmark in the integration suite

`tests/integration/test_overhead_budget.py` (marked `benchmark`) calls the seeded echo upstream directly and through an
endpoint, after warm-up, N = 200 each, sequentially. It prints a table and writes `overhead-report.json`; CI uploads it
as an artifact and appends it to the job summary. The test asserts only that both paths succeeded. The direct path needs
the echo upstream reachable from the test runner, so compose publishes its port on the CI runner (or the test runs in a
container on the compose network).

## Risks / Trade-offs

- [Context leaks into the next request on the same task] → the middleware clears at start and in `finally`; a test
  serves two concurrent requests and checks fields.
- [Access line volume doubles if uvicorn's is not silenced] → `configure_logging` raises `uvicorn.access` above INFO;
  test asserts one access line per request.
- [Migration head check fails during an expand/contract rollout] → by DEP-5 the old code runs against the newer schema;
  the check is "database at or past the head this release knows", treating an unknown newer revision as current. A
  newer revision is detected by it not being in the shipped history.
- [Benchmark is noisy on shared CI runners] → it is a report, not a gate; p95 over 200 samples after warm-up.

## Migration Plan

Additive. New response header `X-Request-Id`; the uvicorn access line is replaced by `http.request` — operators whose
log queries match uvicorn's access format update them (release note). Tracing needs the image built with the extra and
`OTEL_*` set. Rollback: previous image.
