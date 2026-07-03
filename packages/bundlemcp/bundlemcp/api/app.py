"""Gateway application factory: management API, probes; MCP endpoints mount here too."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

from bundlemcp.api.routers import api_keys, bundles, config, endpoints, servers, users
from bundlemcp.bootstrap import run_bootstrap
from bundlemcp.crypto import token_cipher
from bundlemcp.gateway import mcp_endpoint
from bundlemcp.gateway.audit import AuditWriter
from bundlemcp.gateway.discovery import DiscoveryService
from bundlemcp.gateway.mcp_endpoint import GatewayRuntime
from bundlemcp.gateway.metering import load_metering_hook
from bundlemcp.gateway.runtime_config import RuntimeConfig
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.gateway.upstream import ClientFactory, default_client_factory
from bundlemcp.models import ApiKey, ApiKeyKind
from bundlemcp.oauth import authorize as oauth_authorize
from bundlemcp.oauth import metadata as oauth_metadata
from bundlemcp.oauth import oidc as oauth_oidc
from bundlemcp.oauth import registration as oauth_registration
from bundlemcp.oauth import token as oauth_token
from bundlemcp.oauth.adminsessions import AdminSessionStore
from bundlemcp.oauth.oidc import OidcProvider, build_provider
from bundlemcp.oauth.upstream_client import (
    HttpxUpstreamProvider,
    UpstreamOAuthProvider,
    UpstreamTokenStore,
)
from bundlemcp.security import display_prefix, hash_token
from bundlemcp.settings import Settings, get_settings
from bundlemcp.store import create_engine, create_redis, session_factory
from bundlemcp.store.invalidation import InvalidationSubscriber
from bundlemcp.store.sessions import SessionStore

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
    client_factory: ClientFactory | None = None,
    oidc_provider: OidcProvider | None = None,
    upstream_oidc_provider: UpstreamOAuthProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.engine = engine or create_engine(settings.database_url)
        app.state.session_factory = session_factory(app.state.engine)
        app.state.redis = redis or create_redis(settings.redis_url)
        await _ensure_initial_service_key(app, settings)

        factory = client_factory or default_client_factory(settings)
        app.state.discovery = DiscoveryService(app.state.session_factory, factory)
        audit = AuditWriter(app.state.session_factory)
        await audit.start()
        metering = load_metering_hook(settings.metering_hook)
        metering.fail_open = settings.metering_hook_fail_open  # type: ignore[attr-defined]
        runtime_config = RuntimeConfig(app.state.session_factory)
        app.state.runtime_config = runtime_config
        registry = StreamRegistry()
        signals = SignalBus(app.state.redis, registry)  # SES-13
        await signals.start()
        # spec 23: upstream OAuth token store (None if no encryption keys — then
        # upstream_oauth servers error clearly rather than storing plaintext).
        upstream_tokens = None
        if settings.token_encryption_keys:
            upstream_tokens = UpstreamTokenStore(
                app.state.session_factory,
                token_cipher(settings),
                app.state.redis,
                upstream_oidc_provider or HttpxUpstreamProvider(settings),
            )
        app.state.upstream_tokens = upstream_tokens
        app.state.gateway = GatewayRuntime(
            session_store=SessionStore(app.state.redis),
            metering=metering,
            audit=audit,
            client_factory=factory,
            runtime_config=runtime_config,
            registry=registry,
            signals=signals,
            upstream_tokens=upstream_tokens,
            public_url=settings.public_url,
        )
        app.state.admin_sessions = AdminSessionStore(app.state.redis)
        app.state.oidc_provider = oidc_provider or build_provider(settings)
        await run_bootstrap(app.state.session_factory, settings)  # spec 41

        # STP-2: one subscriber per replica; runtime-config cache hangs off it
        subscriber = InvalidationSubscriber(app.state.redis)
        app.state.invalidation = subscriber

        session_store = app.state.gateway.sessions

        async def _on_invalidation(event) -> None:
            if event.entity_type == "config":
                await runtime_config.flush()
                return
            if event.entity_type in ("bundle", "endpoint"):
                # BND-7: live sessions of the affected surface get list_changed.
                # Each replica walks only ITS local streams — full coverage,
                # no extra signaling.
                payload = {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}
                for session_id in registry.broadcast_sessions():
                    record = await session_store.load(session_id)
                    if record is None:
                        continue
                    if (
                        event.entity_type == "bundle" and record.bundle_name == event.key
                    ) or (
                        event.entity_type == "endpoint" and record.endpoint_name == event.key
                    ):
                        registry.deliver_local(session_id, payload)

        subscriber.on_event(_on_invalidation)
        subscriber.on_reconnect_flush(runtime_config.flush)
        await subscriber.start()

        async def _purge_loop() -> None:  # OAS-8/SEC-8
            import asyncio

            while True:
                await asyncio.sleep(600)
                try:
                    removed = await oauth_token.purge_expired(app.state.session_factory)
                    if removed:
                        log.info("oauth.purged", removed=removed)
                except Exception:
                    log.warning("oauth.purge_failed", exc_info=True)

        import asyncio

        purge_task = asyncio.create_task(_purge_loop())
        yield
        purge_task.cancel()
        await signals.stop()
        await subscriber.stop()
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

    for router in (
        servers.router,
        bundles.router,
        endpoints.router,
        api_keys.router,
        config.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    # OAuth server routes at root for .well-known discovery (spec 20)
    for router in (
        oauth_metadata.router,
        oauth_registration.router,
        oauth_authorize.router,
        oauth_token.router,
        oauth_oidc.router,
    ):
        app.include_router(router)
    app.include_router(users.router, prefix=API_PREFIX)  # /api/v1/users (ADM-6, OAS-11)
    app.include_router(mcp_endpoint.router)  # public /{endpoint}/mcp (EP-1)

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
