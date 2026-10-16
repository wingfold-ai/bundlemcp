# ADR-0051: Requests carry one log context, readiness reports each check, and tracing is optional

**Status:** accepted · **Date:** 2026-10-16

## Context

Log lines could not be tied to a request: the logging pipeline merged structlog's context variables, but nothing bound
any, so a failure line said nothing about the request, endpoint, session or caller behind it. The access line was
uvicorn's, whose client is the socket peer, so behind a proxy every request seemed to come from the proxy. `/readyz`
checked that both stores answered but not that the schema matched the code, and could not say which check failed.
There was no tracing.

## Decision drivers

- One place starts and ends a request's context; the places that resolve a fact add it, and nothing else does.
- A field on a log line is an identifier, never a credential or a header value, by construction.
- Readiness names what is missing, and is never an unhandled error.
- Tracing costs nothing while it is off and needs no `BUNDLEMCP_` setting of its own.

## Decision

- **A pure ASGI middleware owns the request context.** It clears the context, binds a fresh `request_id` and the
  `client_ip` the trusted-proxy policy derives, returns the id as `X-Request-Id`, writes one `http.request` line and
  clears the context again. Pure ASGI rather than `BaseHTTPMiddleware`, so the endpoint runs in the same task and the
  fields bound later are on the final line too. Uvicorn's access logger is silenced. A client-supplied request id is
  not adopted, so no client chooses the id of its own lines.
- **Facts are bound where they are resolved**, through one helper whose fields are a closed model: the endpoint and
  the caller in the MCP admission gate, the session in the session adapter, the server and tool in the tool call, the
  caller in the management API's authentication. `domain/` and `application/` only log.
- **Readiness is a report.** The probe checks Postgres, Valkey and the schema separately and returns which failed; the
  route answers 200 or 503 with that report. The schema is current when the database is at the migration head the
  shipped scripts name, or at a revision those scripts do not know, which a newer release wrote.
- **Tracing is an optional extra, switched on by the standard variables.** Only when `OTEL_EXPORTER_OTLP_ENDPOINT`
  (or the traces endpoint) is set does the app import the tracing module, which configures the SDK and instruments
  FastAPI, SQLAlchemy and redis. The span of an upstream call goes through a `CallTracer` contract with a no-op
  default. Routes whose query string carries OAuth codes are not traced.

## Alternatives considered

- **Keep uvicorn's access line and rewrite its client field** with a logging filter. The filter would need the
  settings and the request, which the logging layer does not have.
- **Map SQLAlchemy errors to 503 for `/readyz` with an exception handler.** It hides which check failed.
- **Run the gateway under `opentelemetry-instrument`.** It imports and patches everything even with no exporter
  configured, outside the composition root.
- **Propagate `traceparent` to upstreams.** It adds a header to every upstream request, which interacts with the
  identity-forwarding rules; left to a change that decides it deliberately.

## Consequences

### Positive

- One `X-Request-Id` finds every line of a request, and each line says who and what it is about.
- An orchestrator, and an operator, learn from `/readyz` which dependency is missing.

### Trade-offs

- Operators whose log queries matched uvicorn's access format query `http.request` instead.
- The MCP library imports the OpenTelemetry API, and redis-py the SDK's metrics when the SDK is installed; "zero cost"
  is the gateway's own tracing code, instrumentation and exporter, which load only when configured.
- The published image does not include the tracing extra; tracing needs an image built with it.
