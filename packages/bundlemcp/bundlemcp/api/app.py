"""Gateway application factory: management API, probes; MCP endpoints mount here too."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

from bundlemcp.api.routers import api_keys, bundles, endpoints, servers
from bundlemcp.models import ApiKey, ApiKeyKind
from bundlemcp.security import display_prefix, hash_token
from bundlemcp.settings import Settings, get_settings
from bundlemcp.store import create_engine, create_redis, session_factory

log = structlog.get_logger(__name__)

API_PREFIX = "/api/v1"


async def _ensure_initial_service_key(app: FastAPI, settings: Settings) -> None:
    """BOOT-3-style bootstrap: provision a service key from env if none exists."""
    if not settings.initial_service_key:
        return
    async with app.state.session_factory() as db:
        existing = (
            await db.execute(select(ApiKey).where(ApiKey.kind == ApiKeyKind.SERVICE).limit(1))
        ).scalar_one_or_none()
        if existing is not None:
            return
        db.add(
            ApiKey(
                name="initial-service-key",
                key_hash=hash_token(settings.initial_service_key),
                key_prefix=display_prefix(settings.initial_service_key),
                kind=ApiKeyKind.SERVICE,
            )
        )
        await db.commit()
        log.info("bootstrap.initial_service_key_created")


def create_app(
    settings: Settings | None = None,
    *,
    engine: AsyncEngine | None = None,
    redis: Redis | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.engine = engine or create_engine(settings.database_url)
        app.state.session_factory = session_factory(app.state.engine)
        app.state.redis = redis or create_redis(settings.redis_url)
        await _ensure_initial_service_key(app, settings)
        yield
        await app.state.engine.dispose()
        await app.state.redis.aclose()

    app = FastAPI(
        title="bundlemcp",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",  # API-3
        docs_url=f"{API_PREFIX}/docs",
    )

    for router in (servers.router, bundles.router, endpoints.router, api_keys.router):
        app.include_router(router, prefix=API_PREFIX)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> dict:
        """OBS-3: ready = Postgres and Redis reachable."""
        from sqlalchemy import text

        async with app.state.session_factory() as db:
            await db.execute(text("SELECT 1"))
        await app.state.redis.ping()
        return {"status": "ready"}

    return app
