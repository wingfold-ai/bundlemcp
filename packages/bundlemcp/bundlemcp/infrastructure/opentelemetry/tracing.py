"""OpenTelemetry tracing, imported only when an exporter endpoint is configured.

The SDK is configured from the standard ``OTEL_*`` variables. FastAPI,
SQLAlchemy and redis are instrumented: HTTP request spans, one span per
statement (with placeholders, not values) and one per Valkey command (with its
arguments masked). Routes whose query string carries OAuth codes or state are
not traced at all, so no span records them.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
from opentelemetry.trace import Span, Tracer
from sqlalchemy.ext.asyncio import AsyncEngine

SERVICE_NAME = "bundlemcp-gateway"
# their query strings carry authorization codes and state
UNTRACED_ROUTES = "/oauth/.*,/login.*,/callback.*,/connect.*,/api/v1/upstreams/.*:connect.*"


class OtelSpan:
    def __init__(self, span: Span) -> None:
        self._span = span

    def set_attribute(self, key: str, value: str) -> None:
        self._span.set_attribute(key, value)


class OtelCallTracer:
    """Upstream-call spans on the gateway's tracer, children of the request's span."""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    @contextmanager
    def span(self, name: str, attributes: dict[str, str]) -> Iterator[OtelSpan]:
        with self._tracer.start_as_current_span(name, attributes=attributes) as span:
            yield OtelSpan(span)


class Tracing:
    """The configured provider and its instrumentations, and how to take them down again.

    Built with the app, before it starts, because instrumenting FastAPI adds a
    middleware; the stores are instrumented once the engine exists.
    """

    def __init__(
        self,
        app: FastAPI,
        *,
        processor: SpanProcessor | None = None,
    ) -> None:
        self._app = app
        self._provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
        self._provider.add_span_processor(processor or BatchSpanProcessor(OTLPSpanExporter()))
        FastAPIInstrumentor.instrument_app(
            app, tracer_provider=self._provider, excluded_urls=UNTRACED_ROUTES
        )
        self._redis = RedisInstrumentor()
        self._sqlalchemy = SQLAlchemyInstrumentor()
        self.call_tracer = OtelCallTracer(self._provider.get_tracer("bundlemcp"))

    def instrument_stores(self, engine: AsyncEngine) -> None:
        self._sqlalchemy.instrument(engine=engine.sync_engine, tracer_provider=self._provider)
        self._redis.instrument(tracer_provider=self._provider)

    def shutdown(self) -> None:
        self._redis.uninstrument()
        self._sqlalchemy.uninstrument()
        self._provider.shutdown()
