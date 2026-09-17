"""The composition root: where the app's object graph is wired.

`CompositionRoot` acquires the process-wide collaborators in order, publishes
them as one container on `app.state`, and releases them in reverse on the way
out. It is the one module allowed to name concrete implementations; everything
downstream receives what it needs rather than reaching for it.
"""

from contextlib import AsyncExitStack

import structlog
from fastapi import FastAPI

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.jobs.token_purger import TokenPurger
from bundlemcp.api.oauth.browser_state.oidc_login_state import OidcLoginState
from bundlemcp.api.oauth.browser_state.upstream_connect_state import UpstreamConnectState
from bundlemcp.application.bootstrap import BootstrapRunner
from bundlemcp.application.contracts.identity.oidc_provider import OidcProvider
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.management.api_key_service import ApiKeyService
from bundlemcp.application.oauth_server import (
    AuthorizationCodeGrant,
    MetadataDocumentClientSource,
    PendingAuthorization,
    RefreshTokenGrant,
    RegisteredClientSource,
)
from bundlemcp.application.serving.list_changed_notifier import ListChangedNotifier
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.settings.settings import Settings
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.shared.clock import SystemClock
from bundlemcp.domain.shared.secret_generator import OsSecretGenerator, SecretGenerator
from bundlemcp.domain.shared.secret_hasher import Sha256SecretHasher
from bundlemcp.infrastructure.crypto.token_cipher import token_cipher
from bundlemcp.infrastructure.fastmcp.client_factory import default_client_factory
from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe
from bundlemcp.infrastructure.httpx.client_metadata_fetcher import HttpxClientMetadataFetcher
from bundlemcp.infrastructure.httpx.upstream_oauth_provider import HttpxUpstreamProvider
from bundlemcp.infrastructure.inprocess.counters import InProcessCounters
from bundlemcp.infrastructure.inprocess.stream_registry import InProcessStreamRegistry
from bundlemcp.infrastructure.memory.no_upstream_connections import NoUpstreamConnections
from bundlemcp.infrastructure.metering.hook_loader import load_metering_hook
from bundlemcp.infrastructure.oidc.build_provider import build_provider
from bundlemcp.infrastructure.postgres.audit_writer import QueuedAuditWriter
from bundlemcp.infrastructure.postgres.engine import create_engine, session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.infrastructure.readiness.store_readiness_probe import StoreReadinessProbe
from bundlemcp.infrastructure.valkey.admin_session_store import AdminSessionStore
from bundlemcp.infrastructure.valkey.auth_failure_limiter import ValkeyAuthFailureLimiter
from bundlemcp.infrastructure.valkey.client import create_redis
from bundlemcp.infrastructure.valkey.invalidation_subscriber import InvalidationSubscriber
from bundlemcp.infrastructure.valkey.rate_limiter import ValkeyRateLimiter
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock
from bundlemcp.infrastructure.valkey.session_store import ValkeySessionStore
from bundlemcp.infrastructure.valkey.signal_bus import ValkeySignalBus
from bundlemcp.infrastructure.valkey.valkey_single_use_state import ValkeySingleUseState
from bundlemcp.main.composition_overrides import CompositionOverrides
from bundlemcp.main.container import AppContainer
from bundlemcp.main.mcp_gateway_assembly import McpGatewayAssembly

log = structlog.get_logger(__name__)

# Key layouts of the browser-state records parked in the live store (spec 20, 23).
PENDING_CONSENT_PREFIX = "bmcp:pendingconsent"
OIDC_STATE_PREFIX = "bmcp:oidcstate"
CONNECT_STATE_PREFIX = "bmcp:upstream-connect"
BROWSER_STATE_TTL = 600


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
        clock = overrides.clock or SystemClock()
        hasher = Sha256SecretHasher()
        generator = overrides.secret_generator or OsSecretGenerator()

        engine = overrides.engine or create_engine(settings.database_url)
        if overrides.engine is None:
            self._stack.push_async_callback(engine.dispose)
        sessions = session_factory(engine)
        redis = overrides.redis or create_redis(settings.redis_url)
        if overrides.redis is None:
            self._stack.push_async_callback(redis.aclose)
        units = SqlAlchemyUnitOfWorkFactory(sessions, redis)

        client_factory = overrides.client_factory or default_client_factory(settings)
        discovery = DiscoveryService(units, FastMcpUpstreamProbe(client_factory))

        audit = QueuedAuditWriter(sessions)
        await audit.start()
        self._stack.push_async_callback(audit.stop)

        runtime_config = RuntimeConfig(units)
        registry = InProcessStreamRegistry()
        signals = ValkeySignalBus(redis, registry)  # SES-13
        await signals.start()
        self._stack.push_async_callback(signals.stop)
        session_store = ValkeySessionStore(redis)

        cipher = self._build_cipher()
        upstream_tokens = (
            UpstreamTokenService(
                units,
                cipher,
                ValkeyRefreshLock(redis),
                overrides.upstream_oidc_provider or HttpxUpstreamProvider(settings),
            )
            if cipher is not None
            else None
        )

        counters = overrides.counters or InProcessCounters()  # RATE-3 metric seam
        auth_failure_limiter = overrides.auth_failure_limiter or ValkeyAuthFailureLimiter(  # RATE-5
            redis,
            limit=settings.auth_failure_limit,
            window=settings.auth_failure_window,
            counters=counters,
        )
        auth_failure_guard = AuthFailureGuard(auth_failure_limiter, settings)
        rate_limiter = overrides.rate_limiter or ValkeyRateLimiter(redis, counters)
        mcp_router = McpGatewayAssembly(
            settings=settings,
            unit_of_work_factory=units,
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
            clock=clock,
            secret_hasher=hasher,
        ).build()

        await self._ensure_initial_service_key(units, hasher, generator)
        await BootstrapRunner(units, discovery).run(settings)  # spec 41

        subscriber = InvalidationSubscriber(redis)  # STP-2: one subscriber per replica
        subscriber.on_reconnect_flush(runtime_config.flush)
        subscriber.on_event(self._config_flush(runtime_config))
        subscriber.on_event(ListChangedNotifier(registry).on_invalidation)
        await subscriber.start()
        self._stack.push_async_callback(subscriber.stop)
        self._stack.callback(registry.close_streams)  # PROT-17: streams end with a result

        purger = TokenPurger(units, clock)  # OAS-8/SEC-8: expired grants must not linger
        purger.start()
        self._stack.callback(purger.stop)

        client_metadata = overrides.client_metadata_fetcher or HttpxClientMetadataFetcher(
            settings, redis
        )

        return AppContainer(
            settings=settings,
            clock=clock,
            secret_hasher=hasher,
            secret_generator=generator,
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
            readiness=StoreReadinessProbe(sessions, redis),
            pending_authorizations=ValkeySingleUseState(
                redis,
                prefix=PENDING_CONSENT_PREFIX,
                ttl_seconds=BROWSER_STATE_TTL,
                model=PendingAuthorization,
            ),
            oidc_login_states=ValkeySingleUseState(
                redis, prefix=OIDC_STATE_PREFIX, ttl_seconds=BROWSER_STATE_TTL, model=OidcLoginState
            ),
            connect_states=ValkeySingleUseState(
                redis,
                prefix=CONNECT_STATE_PREFIX,
                ttl_seconds=BROWSER_STATE_TTL,
                model=UpstreamConnectState,
            ),
            oidc_provider=await self._build_oidc_provider(),
            invalidation=subscriber,
            mcp_router=mcp_router,
            client_metadata=client_metadata,
            # OAS-4: the grants this server serves; OAS-2/OAS-13: how clients identify
            token_grants=(AuthorizationCodeGrant, RefreshTokenGrant),
            client_sources=(
                lambda uow: RegisteredClientSource(uow.oauth_clients),
                lambda uow: MetadataDocumentClientSource(uow.oauth_clients, client_metadata),
            ),
        )

    def _build_cipher(self) -> SecretCipher | None:
        # spec 23 / DEP-9: without keys nothing is stored, so upstream_oauth
        # servers error clearly rather than storing plaintext.
        if not self._settings.token_encryption_keys:
            return None
        return token_cipher(self._settings)

    async def _ensure_initial_service_key(
        self,
        units: SqlAlchemyUnitOfWorkFactory,
        hasher: Sha256SecretHasher,
        generator: OsSecretGenerator | SecretGenerator,
    ) -> None:
        if not self._settings.initial_service_key:
            return
        async with units.open() as uow:
            await ApiKeyService(uow, hasher=hasher, generator=generator).ensure_initial_service_key(
                self._settings.initial_service_key
            )

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
