"""Gateway application factory: management API, probes; MCP endpoints mount here too."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from bundlemcp.api.routers import api_keys, audit, bundles, endpoints, servers
from bundlemcp.gateway import mcp_endpoint
from bundlemcp.gateway.audit import AuditWriter
from bundlemcp.gateway.discovery import DiscoveryService
from bundlemcp.gateway.mcp_endpoint import GatewayRuntime
from bundlemcp.gateway.metering import load_metering_hook
from bundlemcp.gateway.metrics import Counters
from bundlemcp.gateway.upstream import ClientFactory, default_client_factory
from bundlemcp.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PreconditionError,
    ServiceError,
    UnavailableError,
)
from bundlemcp.settings import Settings, get_settings
from bundlemcp.store import create_engine, create_redis, session_factory
from bundlemcp.store.sessions import SessionStore

log = structlog.get_logger(__name__)

API_PREFIX = "/api/v1"

# Domain errors raised by the service layer, mapped to HTTP here so services
# stay framework-free.
_SERVICE_ERROR_STATUS: dict[type[ServiceError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    PreconditionError: status.HTTP_400_BAD_REQUEST,
    UnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    code = _SERVICE_ERROR_STATUS.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(status_code=code, content={"detail": str(exc)})


def create_app(
    settings: Settings | None = None,
    *,
    engine: AsyncEngine | None = None,
    redis: Redis | None = None,
    client_factory: ClientFactory | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.engine = engine or create_engine(settings.database_url)
        app.state.session_factory = session_factory(app.state.engine)
        app.state.redis = redis or create_redis(settings.redis_url)

        factory = client_factory or default_client_factory(settings)
        app.state.discovery = DiscoveryService(app.state.session_factory, factory)
        audit = AuditWriter(app.state.session_factory)
        await audit.start()
        metering = load_metering_hook(settings.metering_hook)
        metering.fail_open = settings.metering_hook_fail_open  # type: ignore[attr-defined]
        counters = Counters()  # metric seam (spec 51 exports these)
        app.state.counters = counters
        app.state.gateway = GatewayRuntime(
            session_store=SessionStore(app.state.redis),
            metering=metering,
            audit=audit,
            client_factory=factory,
            public_url=settings.public_url,
            counters=counters,
            settings=settings,
        )
        yield
        await audit.stop()
        await app.state.engine.dispose()
        await app.state.redis.aclose()

    app = FastAPI(
        title="bundlemcp",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",  # API-3
        docs_url=f"{API_PREFIX}/docs",
    )
    app.add_exception_handler(ServiceError, _service_error_handler)

    if settings.web_origins:
        # SEC-4: credentials-enabled CORS for exactly the web app's origin(s)
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.rstrip("/") for o in settings.web_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["Mcp-Session-Id"],
        )

    for router in (
        servers.router,
        bundles.router,
        endpoints.router,
        api_keys.router,
        audit.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    app.include_router(mcp_endpoint.router)  # public /{endpoint}/mcp (EP-1)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> dict:
        """Ready means both Postgres and Redis are reachable."""
        from sqlalchemy import text

        async with app.state.session_factory() as db:
            await db.execute(text("SELECT 1"))
        await app.state.redis.ping()
        return {"status": "ready"}

    return app
