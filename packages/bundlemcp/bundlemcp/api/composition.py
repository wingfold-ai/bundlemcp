"""The composition root: where the app's object graph is wired.

`CompositionRoot` acquires the process-wide collaborators in order, publishes
them onto `app.state`, and releases them in reverse on the way out. It is the
one module allowed to name concrete implementations; everything downstream
receives what it needs rather than reaching for it.
"""

import asyncio
from contextlib import AsyncExitStack

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

from bundlemcp.bootstrap import run_bootstrap
from bundlemcp.crypto import token_cipher
from bundlemcp.gateway.audit import AuditWriter
from bundlemcp.gateway.discovery import DiscoveryService
from bundlemcp.gateway.mcp_endpoint import GatewayRuntime
from bundlemcp.gateway.metering import load_metering_hook
from bundlemcp.gateway.metrics import Counters
from bundlemcp.gateway.ratelimit import AuthFailureLimiter, RateLimiter
from bundlemcp.gateway.runtime_config import RuntimeConfig
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.gateway.upstream import ClientFactory, default_client_factory
from bundlemcp.models import ApiKey, ApiKeyKind
from bundlemcp.oauth import token as oauth_token
from bundlemcp.oauth.adminsessions import AdminSessionStore
from bundlemcp.oauth.oidc import OidcProvider, build_provider
from bundlemcp.oauth.upstream_client import (
    HttpxUpstreamProvider,
    UpstreamOAuthProvider,
    UpstreamTokenStore,
)
from bundlemcp.security import display_prefix, hash_token
from bundlemcp.settings import Settings
from bundlemcp.store import create_engine, create_redis, session_factory
from bundlemcp.store.invalidation import InvalidationSubscriber
from bundlemcp.store.sessions import SessionStore

log = structlog.get_logger(__name__)


class CompositionRoot:
    """Owns the app's startup sequence and everything it acquires.

    Each step registers its own teardown on a stack this object owns, so entry
    and exit stay symmetric: the stack unwinds in reverse acquisition order, and
    a failure partway through startup releases exactly what was acquired so far.

    Every keyword argument is a composition seam: each falls back to the real
    implementation when None, so tests can substitute one without the others.
    """

    def __init__(
        self,
        app: FastAPI,
        settings: Settings,
        *,
        engine: AsyncEngine | None = None,
        redis: Redis | None = None,
        client_factory: ClientFactory | None = None,
        oidc_provider: OidcProvider | None = None,
        upstream_oidc_provider: UpstreamOAuthProvider | None = None,
    ) -> None:
        # Starlette builds app.state once and never rebinds it, so holding the
        # reference here saves every method from reaching through the app.
        self._state = app.state
        self._settings = settings
        self._engine = engine
        self._redis = redis
        self._client_factory = client_factory
        self._oidc_provider = oidc_provider
        self._upstream_oidc_provider = upstream_oidc_provider
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> "CompositionRoot":
        try:
            await self._compose()
        except BaseException:
            # __aexit__ never runs for a failed __aenter__, so unwind here.
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    async def _compose(self) -> None:
        """The build sequence, in dependency order.

        Deliberately private: composing without the surrounding ``async with``
        would acquire resources nothing is obliged to release.
        """
        await self._open_stores()
        await self._ensure_initial_service_key()
        await self._build_gateway_runtime()
        await self._setup_auth()
        await self._run_bootstrap()
        await self._start_invalidation()
        self._start_purge_loop()

    async def _open_stores(self) -> None:
        """Attach the durable store (Postgres) and the live store (Valkey) to app.state.

        Only self-created connections are closed on shutdown; an injected engine
        or client stays owned by whoever passed it in, so it survives for reuse.
        """
        self._state.settings = self._settings
        self._state.engine = self._engine or create_engine(self._settings.database_url)
        if self._engine is None:
            self._stack.push_async_callback(self._state.engine.dispose)
        self._state.session_factory = session_factory(self._state.engine)
        self._state.redis = self._redis or create_redis(self._settings.redis_url)
        if self._redis is None:
            self._stack.push_async_callback(self._state.redis.aclose)

    async def _ensure_initial_service_key(self) -> None:
        """Provision a service API key from the environment if none exists yet."""
        if not self._settings.initial_service_key:
            return
        key = self._settings.initial_service_key
        async with self._state.session_factory() as db:
            existing = (
                await db.execute(select(ApiKey).where(ApiKey.kind == ApiKeyKind.SERVICE).limit(1))
            ).scalar_one_or_none()
            if existing is not None:
                return
            db.add(
                ApiKey(
                    name="initial-service-key",
                    key_hash=hash_token(key),
                    key_prefix=display_prefix(key),
                    kind=ApiKeyKind.SERVICE,
                )
            )
            await db.commit()
            log.info("bootstrap.initial_service_key_created")

    def _build_upstream_tokens(self) -> UpstreamTokenStore | None:
        """Store for upstream OAuth tokens, or None when no encryption keys are configured."""
        # spec 23: without keys the store stays None, so upstream_oauth servers
        # error clearly rather than storing plaintext.
        if not self._settings.token_encryption_keys:
            return None
        return UpstreamTokenStore(
            self._state.session_factory,
            token_cipher(self._settings),
            self._state.redis,
            self._upstream_oidc_provider or HttpxUpstreamProvider(self._settings),
        )

    async def _build_gateway_runtime(self) -> None:
        """Assemble GatewayRuntime and publish its collaborators onto app.state."""
        factory = self._client_factory or default_client_factory(self._settings)
        self._state.discovery = DiscoveryService(self._state.session_factory, factory)

        audit = AuditWriter(self._state.session_factory)
        await audit.start()
        self._stack.push_async_callback(audit.stop)

        metering = load_metering_hook(self._settings.metering_hook)

        runtime_config = RuntimeConfig(self._state.session_factory)
        self._state.runtime_config = runtime_config

        registry = StreamRegistry()
        signals = SignalBus(self._state.redis, registry)  # SES-13
        await signals.start()
        self._stack.push_async_callback(signals.stop)

        upstream_tokens = self._build_upstream_tokens()
        self._state.upstream_tokens = upstream_tokens

        counters = Counters()  # RATE-3 metric seam (spec 51 exports these)
        self._state.counters = counters
        auth_failure_limiter = AuthFailureLimiter(  # RATE-5
            self._state.redis,
            limit=self._settings.auth_failure_limit,
            window=self._settings.auth_failure_window,
            counters=counters,
        )
        self._state.auth_failure_limiter = auth_failure_limiter
        self._state.gateway = GatewayRuntime(
            sessions=SessionStore(self._state.redis),
            metering=metering,
            audit=audit,
            client_factory=factory,
            runtime_config=runtime_config,
            registry=registry,
            signals=signals,
            upstream_tokens=upstream_tokens,
            public_url=self._settings.public_url,
            rate_limiter=RateLimiter(self._state.redis, counters),
            counters=counters,
            settings=self._settings,
        )

    async def _setup_auth(self) -> None:
        """Admin session store plus the OIDC provider, with its metadata preloaded."""
        self._state.admin_sessions = AdminSessionStore(self._state.redis)
        provider = self._oidc_provider or build_provider(self._settings)
        self._state.oidc_provider = provider
        preload = getattr(provider, "preload", None)
        if preload is not None:
            try:
                await preload()  # authorize_url needs the discovered metadata
            except Exception:
                log.warning("oidc.preload_failed", exc_info=True)

    async def _run_bootstrap(self) -> None:
        # spec 41
        await run_bootstrap(self._state.session_factory, self._state.redis, self._settings)

    async def _start_invalidation(self) -> None:
        """Subscribe this replica to config invalidation and live tool-list changes."""
        # Captured once so the callback reads a stable object graph instead of
        # re-reaching through app.state on every event.
        gateway = self._state.gateway
        registry = gateway.registry
        runtime_config = gateway.runtime_config
        session_store = gateway.sessions

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
                    if (event.entity_type == "bundle" and record.bundle_name == event.key) or (
                        event.entity_type == "endpoint" and record.endpoint_name == event.key
                    ):
                        registry.deliver_local(session_id, payload)

        # STP-2: one subscriber per replica; runtime-config cache hangs off it
        subscriber = InvalidationSubscriber(self._state.redis)
        self._state.invalidation = subscriber
        subscriber.on_event(_on_invalidation)
        subscriber.on_reconnect_flush(runtime_config.flush)
        await subscriber.start()
        self._stack.push_async_callback(subscriber.stop)

    def _start_purge_loop(self) -> None:
        # OAS-8/SEC-8: expired grants and tokens must not linger in the database.
        task = asyncio.create_task(oauth_token.purge_expired_forever(self._state.session_factory))
        self._stack.callback(task.cancel)
