"""The composition root: where the app's object graph is wired.

`CompositionRoot` acquires the process-wide collaborators in order, publishes
them as one container on `app.state`, and releases them in reverse on the way
out. It is the one module allowed to name concrete implementations; everything
downstream receives what it needs rather than reaching for it.
"""

from contextlib import AsyncExitStack

import structlog
from fastapi import FastAPI

from bundlemcp.api.composition_overrides import CompositionOverrides
from bundlemcp.api.container import AppContainer
from bundlemcp.bootstrap import BootstrapRunner
from bundlemcp.crypto import TokenCipher, token_cipher
from bundlemcp.gateway.audit import AuditWriter
from bundlemcp.gateway.discovery import DiscoveryService
from bundlemcp.gateway.list_changed_notifier import ListChangedNotifier
from bundlemcp.gateway.mcp_endpoint import McpEdgeAssembly
from bundlemcp.gateway.metering import load_metering_hook
from bundlemcp.gateway.metrics import Counters
from bundlemcp.gateway.ratelimit import AuthFailureGuard, AuthFailureLimiter, RateLimiter
from bundlemcp.gateway.runtime_config import RuntimeConfig
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.gateway.upstream import default_client_factory
from bundlemcp.oauth.client_metadata_fetcher import HttpxClientMetadataFetcher
from bundlemcp.oauth.oidc import OidcProvider, build_provider
from bundlemcp.oauth.token_purger import TokenPurger
from bundlemcp.oauth.upstream_client import HttpxUpstreamProvider, UpstreamTokenStore
from bundlemcp.services import ApiKeyService, NoUpstreamConnections
from bundlemcp.settings import Settings
from bundlemcp.store import UnitOfWorkFactory, create_engine, create_redis, session_factory
from bundlemcp.store.admin_sessions import AdminSessionStore
from bundlemcp.store.invalidation import InvalidationSubscriber
from bundlemcp.store.sessions import SessionStore

log = structlog.get_logger(__name__)


class CompositionRoot:
    """Owns the app's startup sequence and everything it acquires.

    Each step registers its own teardown on a stack this object owns, so entry
    and exit stay symmetric: the stack unwinds in reverse acquisition order, and
    a failure partway through startup releases exactly what was acquired so far.
    """

    def __init__(self, app: FastAPI, settings: Settings, overrides: CompositionOverrides) -> None:
        # Starlette builds app.state once and never rebinds it, so holding the
        # reference here saves every method from reaching through the app.
        self._state = app.state
        self._settings = settings
        self._overrides = overrides
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> "CompositionRoot":
        try:
            self._state.container = await self._compose()
        except BaseException:
            # __aexit__ never runs for a failed __aenter__, so unwind here.
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    async def _compose(self) -> AppContainer:
        """The build sequence, in dependency order.

        Deliberately private: composing without the surrounding ``async with``
        would acquire resources nothing is obliged to release.
        """
        settings = self._settings
        overrides = self._overrides

        engine = overrides.engine or create_engine(settings.database_url)
        if overrides.engine is None:
            self._stack.push_async_callback(engine.dispose)
        sessions = session_factory(engine)
        redis = overrides.redis or create_redis(settings.redis_url)
        if overrides.redis is None:
            self._stack.push_async_callback(redis.aclose)
        units = UnitOfWorkFactory(sessions, redis)

        client_factory = overrides.client_factory or default_client_factory(settings)
        discovery = DiscoveryService(sessions, client_factory)

        audit = AuditWriter(sessions)
        await audit.start()
        self._stack.push_async_callback(audit.stop)

        runtime_config = RuntimeConfig(sessions)
        registry = StreamRegistry()
        signals = SignalBus(redis, registry)  # SES-13
        await signals.start()
        self._stack.push_async_callback(signals.stop)
        session_store = SessionStore(redis)

        cipher = self._build_cipher()
        upstream_tokens = (
            UpstreamTokenStore(
                sessions,
                cipher,
                redis,
                overrides.upstream_oidc_provider or HttpxUpstreamProvider(settings),
            )
            if cipher is not None
            else None
        )

        counters = overrides.counters or Counters()  # RATE-3 metric seam
        auth_failure_limiter = overrides.auth_failure_limiter or AuthFailureLimiter(  # RATE-5
            redis,
            limit=settings.auth_failure_limit,
            window=settings.auth_failure_window,
            counters=counters,
        )
        auth_failure_guard = AuthFailureGuard(auth_failure_limiter, settings)
        rate_limiter = overrides.rate_limiter or RateLimiter(redis, counters)
        mcp_edge = McpEdgeAssembly(
            settings=settings,
            session_factory=sessions,
            sessions=session_store,
            registry=registry,
            signals=signals,
            metering=overrides.metering_hook or load_metering_hook(settings.metering_hook),
            audit=audit,
            client_factory=client_factory,
            runtime_config=runtime_config,
            upstream_tokens=upstream_tokens,
            state_cipher=cipher,
            rate_limiter=rate_limiter,
            auth_failures=auth_failure_guard,
            counters=counters,
        ).build()

        await self._ensure_initial_service_key(units)
        await BootstrapRunner(units, discovery).run(settings)  # spec 41

        subscriber = InvalidationSubscriber(redis)  # STP-2: one subscriber per replica
        subscriber.on_reconnect_flush(runtime_config.flush)
        subscriber.on_event(self._config_flush(runtime_config))
        subscriber.on_event(ListChangedNotifier(registry).on_invalidation)
        await subscriber.start()
        self._stack.push_async_callback(subscriber.stop)
        self._stack.callback(registry.close_streams)  # PROT-17: streams end with a result

        purger = TokenPurger(units)  # OAS-8/SEC-8: expired grants must not linger
        purger.start()
        self._stack.callback(purger.stop)

        return AppContainer(
            settings=settings,
            engine=engine,
            session_factory=sessions,
            redis=redis,
            unit_of_work_factory=units,
            discovery=discovery,
            audit=audit,
            runtime_config=runtime_config,
            counters=counters,
            rate_limiter=rate_limiter,
            auth_failure_limiter=auth_failure_limiter,
            auth_failure_guard=auth_failure_guard,
            token_cipher=cipher,
            upstream_tokens=upstream_tokens,
            upstream_connections=upstream_tokens or NoUpstreamConnections(),
            admin_sessions=AdminSessionStore(redis),
            oidc_provider=await self._build_oidc_provider(),
            invalidation=subscriber,
            mcp_edge=mcp_edge,
            client_metadata=overrides.client_metadata_fetcher
            or HttpxClientMetadataFetcher(settings, redis),
        )

    def _build_cipher(self) -> TokenCipher | None:
        # spec 23 / DEP-9: without keys nothing is stored, so upstream_oauth
        # servers error clearly rather than storing plaintext.
        if not self._settings.token_encryption_keys:
            return None
        return token_cipher(self._settings)

    async def _ensure_initial_service_key(self, units: UnitOfWorkFactory) -> None:
        if not self._settings.initial_service_key:
            return
        async with units.open() as uow:
            await ApiKeyService(uow).ensure_initial_service_key(self._settings.initial_service_key)

    async def _build_oidc_provider(self) -> OidcProvider | None:
        """The configured identity provider, ready to build authorize URLs."""
        if self._overrides.oidc_provider is not None:
            return self._overrides.oidc_provider
        try:
            return await build_provider(self._settings)
        except Exception:
            log.warning("oidc.discovery_failed", exc_info=True)
            return None

    @staticmethod
    def _config_flush(runtime_config: RuntimeConfig):
        async def on_event(event) -> None:
            if event.entity_type == "config":
                await runtime_config.flush()

        return on_event
