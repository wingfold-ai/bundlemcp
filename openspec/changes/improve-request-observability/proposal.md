# Proposal: improve request observability

## Why

Log lines today cannot be tied to a request: the logging pipeline merges structlog contextvars, but nothing binds any,
so a `discovery.failed` or `metering.post_call_failed` line says nothing about which request, endpoint, session or
caller it belongs to. The access log records the socket peer — the reverse proxy — instead of the client IP the
trusted-proxy policy derives. `/readyz` checks that the stores answer but not that the schema is current, and a Postgres
failure surfaces as an unhandled 500 rather than "not ready". There is no tracing and no measurement of what the gateway
adds to a `tools/call`.

## What Changes

- Every log line written while serving a request carries a request id, the endpoint, the MCP session id and the caller
  (user id or API key id) once each is resolved, and the client IP derived from the trusted-proxy policy (OPS-8,
  DEP-2's logging clause).
- The log stream is stated explicitly (OPS-8); see the open decision below.
- `/readyz` also reports not-ready while the database schema is behind the code, and answers 503 — never 500 — when
  Postgres is unreachable (OPS-10, DEP-4).
- Optional OpenTelemetry tracing, off by default and zero-cost when off, with a span per upstream tool call (OPS-12).
- The integration suite measures the gateway's added latency on `tools/call` and reports it against a 50 ms p95 budget
  — a report, not a gate (OPS-13).

## Open decision

**Log stream: stdout or stderr?** The original OPS-8 said "JSON to stdout"; the code writes to **stderr**
(`logging.StreamHandler()` default) and its docstrings say stdout. Container runtimes collect both, so the choice is
about convention and about tooling that reads only one stream. The delta below keeps **stderr** (what ships today, no
behaviour change); if the maintainers choose stdout, OPS-8's delta changes one word and task 1.1 switches the handler.
Decide before applying. Either way the docstrings are corrected (in
[fix-stale-documentation](../archive/2026-10-13-fix-stale-documentation/proposal.md) until this lands).

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `operations`: MODIFIED OPS-8 (request context on every line; stated stream) and OPS-10 (`/readyz` checks migrations;
  Postgres failure is 503); ADDED OPS-12 (optional OpenTelemetry tracing) and OPS-13 (overhead budget report).
- `deployment`: MODIFIED DEP-4 (`/readyz` false until the schema is current) and DEP-2 (the derived client IP is also
  used in logging).

## Impact

- **Code:** a pure ASGI request-context middleware in `api/http/`; binding points in the MCP admission gate, session
  adapter and management auth; a schema-currency check in the readiness probe (`infrastructure/readiness/`); an optional
  tracing adapter in `infrastructure/` loaded by `main/` only when configured; an integration-suite overhead benchmark.
- **Dependencies:** OpenTelemetry packages as an optional extra (`bundlemcp[otel]`), not installed by default; the
  gateway image decides whether to include it.
- **Responses:** every HTTP response carries an `X-Request-Id` header.
- **Overlap:** [harden-http-edge](../archive/2026-10-15-harden-http-edge/proposal.md) changed DEP-2 first (rightmost
  untrusted `X-Forwarded-For` entry; `X-Forwarded-Proto/Host` ignored). This change's DEP-2 delta is that text plus
  its own logging clause.
- **Dependents:** [add-live-logs](../add-live-logs/proposal.md) filters by server and endpoint using the context this
  change binds.
- **ADR:** one ADR (next free number) for the request-context and tracing model.
