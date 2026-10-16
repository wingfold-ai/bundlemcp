"""The composition root: where the app's object graph is wired.

`CompositionRoot` acquires the process-wide collaborators in order, publishes
them as one container on `app.state`, and releases them in reverse on the way
out. It is the one module allowed to name concrete implementations; everything
downstream receives what it needs rather than reaching for it.
"""

from contextlib import AsyncExitStack
from typing import Any

from fastapi import FastAPI

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.jobs.invocation_sweep_job import InvocationSweepJob
from bundlemcp.api.jobs.secret_reencryption_job import SecretReencryptionJob
from bundlemcp.api.jobs.session_sweep_job import SessionSweepJob
from bundlemcp.api.jobs.token_purger import TokenPurger
from bundlemcp.api.jobs.tool_refresher import ToolRefresher
from bundlemcp.api.mcp.protocol.sse import KEEPALIVE_SECONDS
from bundlemcp.api.oauth.browser_state.oidc_login_state import OidcLoginState
from bundlemcp.api.oauth.browser_state.upstream_connect_state import UpstreamConnectState
from bundlemcp.application.bootstrap import BootstrapRunner
from bundlemcp.application.contracts.identity.oidc_provider import OidcProvider
from bundlemcp.application.contracts.observability.call_tracer import CallTracer
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.delegation.delegated_token_issuer import DelegatedTokenIssuer
from bundlemcp.application.discovery.connection_diagnoser import ConnectionDiagnoser
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.discovery.upstream_health import UpstreamHealth
from bundlemcp.application.management.api_key_service import ApiKeyService
from bundlemcp.application.metering.invocation_sweeper import InvocationSweeper
from bundlemcp.application.oauth_server import (
    AuthorizationCodeGrant,
    MetadataDocumentClientSource,
    PendingAuthorization,
    RefreshTokenGrant,
    RegisteredClientSource,
)
from bundlemcp.application.serving.list_changed_notifier import ListChangedNotifier
from bundlemcp.application.serving.replica_drain import ReplicaDrain
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.sessions.session_sweeper import SessionSweeper
from bundlemcp.application.settings.settings import Settings
from bundlemcp.application.upstream_oauth.secret_reencryption import SecretReencryption
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog
from bundlemcp.domain.oauth.redirect_uri_allow_list import RedirectUriAllowList
from bundlemcp.domain.oauth.registration_policy import RegistrationPolicy
from bundlemcp.domain.shared.os_secret_generator import OsSecretGenerator
from bundlemcp.domain.shared.secret_generator import SecretGenerator
from bundlemcp.domain.shared.sha256_secret_hasher import Sha256SecretHasher
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.crypto.token_cipher import token_cipher
from bundlemcp.infrastructure.fastmcp.client_factory import default_client_factory
from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe
from bundlemcp.infrastructure.httpx.client_metadata_fetcher import HttpxClientMetadataFetcher
from bundlemcp.infrastructure.httpx.upstream_oauth_provider import HttpxUpstreamProvider
from bundlemcp.infrastructure.inprocess.counters import InProcessCounters
from bundlemcp.infrastructure.inprocess.stream_registry import InProcessStreamRegistry
from bundlemcp.infrastructure.memory.no_upstream_connections import NoUpstreamConnections
from bundlemcp.infrastructure.memory.noop_call_tracer import NoopCallTracer
from bundlemcp.infrastructure.metering.hook_loader import load_metering_hook
from bundlemcp.infrastructure.metering.http_metering_hook import HttpMeteringHook
from bundlemcp.infrastructure.oidc.build_provider import build_provider
from bundlemcp.infrastructure.postgres.audit_writer import QueuedAuditWriter
from bundlemcp.infrastructure.postgres.engine import create_engine, session_factory
from bundlemcp.infrastructure.postgres.shipped_migrations import ShippedMigrations
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.infrastructure.readiness.store_readiness_probe import StoreReadinessProbe
from bundlemcp.infrastructure.valkey.admin_session_store import AdminSessionStore
from bundlemcp.infrastructure.valkey.auth_failure_limiter import ValkeyAuthFailureLimiter
from bundlemcp.infrastructure.valkey.client import create_redis
from bundlemcp.infrastructure.valkey.delegated_token_store import ValkeyDelegatedTokenStore
from bundlemcp.infrastructure.valkey.failure_streak_store import ValkeyFailureStreak
from bundlemcp.infrastructure.valkey.invalidation_subscriber import InvalidationSubscriber
from bundlemcp.infrastructure.valkey.paused_invocations import ValkeyPausedInvocations
from bundlemcp.infrastructure.valkey.rate_limiter import ValkeyRateLimiter
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock
from bundlemcp.infrastructure.valkey.session_store import ValkeySessionStore
from bundlemcp.infrastructure.valkey.signal_bus import ValkeySignalBus
from bundlemcp.infrastructure.valkey.stream_presence_store import ValkeyStreamPresence
from bundlemcp.infrastructure.valkey.valkey_single_use_state import ValkeySingleUseState
from bundlemcp.main.composition_overrides import CompositionOverrides
from bundlemcp.main.container import AppContainer
from bundlemcp.main.mcp_gateway_assembly import McpGatewayAssembly

# Where the gateway publishes its own client metadata document for upstreams.
UPSTREAM_CLIENT_DOCUMENT_PATH = "/oauth/upstream/client.json"

# Key layouts of the browser-state records parked in the live store (OAuth server, upstream OAuth).
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

    def __init__(
        self,
        app: FastAPI,
        settings: Settings,
        overrides: CompositionOverrides,
        tracing: Any = None,
    ) -> None:
        # Starlette builds app.state once and never rebinds it, so holding the
        # reference here saves every method from reaching through the app.
        # tracing is None unless an OpenTelemetry exporter is configured.
        self._state = app.state
        self._settings = settings
        self._overrides = overrides
        self._tracing = tracing
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
        tracer: CallTracer = NoopCallTracer()
        if self._tracing is not None:
            self._tracing.instrument_stores(engine)
            self._stack.callback(self._tracing.shutdown)
            tracer = self._tracing.call_tracer
        sessions = session_factory(engine)
        redis = overrides.redis or create_redis(settings.redis_url)
        if overrides.redis is None:
            self._stack.push_async_callback(redis.aclose)
        units = SqlAlchemyUnitOfWorkFactory(sessions, redis)

        runtime_config = RuntimeConfig(units, cache_disabled=settings.config_cache_disabled)
        client_factory = overrides.client_factory or default_client_factory(
            settings, lambda: runtime_config.current("max_upstream_response_bytes")
        )

        cipher = self._build_cipher()
        upstream_oauth = overrides.upstream_oidc_provider or HttpxUpstreamProvider(settings)
        upstream_tokens = (
            UpstreamTokenService(
                units,
                cipher,
                ValkeyRefreshLock(redis),
                upstream_oauth,
                metadata_document_url=self._client_document_url(),
            )
            if cipher is not None
            else None
        )
        delegated_tokens = DelegatedTokenIssuer(
            ValkeyDelegatedTokenStore(redis), clock=clock, generator=generator, hasher=hasher
        )
        upstream_probe = FastMcpUpstreamProbe(client_factory)
        diagnoser = ConnectionDiagnoser(upstream_oauth)
        # upstream-OAuth servers are probed with a connected account's token
        # one failure streak per upstream, shared by every replica
        upstream_health = UpstreamHealth(units, ValkeyFailureStreak(redis), runtime_config)
        discovery = DiscoveryService(
            units,
            upstream_probe,
            health=upstream_health,
            credentials=UpstreamCredentialResolver(
                upstream_tokens, settings.public_base, delegated=delegated_tokens
            ),
            diagnoser=diagnoser,
        )

        audit = QueuedAuditWriter(sessions)
        await audit.start()
        self._stack.push_async_callback(audit.stop)

        registry = InProcessStreamRegistry()
        drain = ReplicaDrain(registry, settings.shutdown_drain_seconds)
        self._stack.callback(drain.stop)
        signals = ValkeySignalBus(redis, registry)
        await signals.start()
        self._stack.push_async_callback(signals.stop)
        session_store = ValkeySessionStore(redis)

        counters = overrides.counters or InProcessCounters()  # metric seam
        profiles = overrides.profiles or ProfileCatalog.builtin()
        auth_failure_limiter = overrides.auth_failure_limiter or ValkeyAuthFailureLimiter(
            redis,
            limit=settings.auth_failure_limit,
            window=settings.auth_failure_window,
            counters=counters,
        )
        auth_failure_guard = AuthFailureGuard(auth_failure_limiter, settings)
        rate_limiter = overrides.rate_limiter or ValkeyRateLimiter(redis, counters)
        metering = overrides.metering_hook or load_metering_hook(settings)
        if isinstance(metering, HttpMeteringHook):
            self._stack.push_async_callback(metering.aclose)
        paused_invocations = ValkeyPausedInvocations(redis)
        mcp_router = McpGatewayAssembly(
            settings=settings,
            unit_of_work_factory=units,
            sessions=session_store,
            registry=registry,
            drain=drain,
            # a holder is believed for three missed keep-alives at most
            presence=ValkeyStreamPresence(redis, hold_seconds=3 * KEEPALIVE_SECONDS),
            signals=signals,
            metering=metering,
            paused_invocations=paused_invocations,
            audit=audit,
            client_factory=client_factory,
            runtime_config=runtime_config,
            upstream_health=upstream_health,
            tracer=tracer,
            upstream_tokens=upstream_tokens,
            delegated_tokens=delegated_tokens,
            state_cipher=cipher,
            rate_limiter=rate_limiter,
            auth_failures=auth_failure_guard,
            counters=counters,
            profiles=profiles,
            clock=clock,
            secret_hasher=hasher,
        ).build()

        await self._ensure_initial_service_key(units, hasher, generator)
        await BootstrapRunner(  # the management spec
            units,
            discovery,
            cipher=cipher,
            connections=upstream_tokens or NoUpstreamConnections(),
            profiles=profiles,
            public_base=settings.public_base,
        ).run(settings)

        subscriber = InvalidationSubscriber(redis)  # one subscriber per replica
        await runtime_config.refresh()  # the snapshot holds stored values before serving
        # a gap only drops the cache: the next config read reloads it, snapshot included,
        # without a load racing the requests that are already being served
        subscriber.on_reconnect_flush(runtime_config.flush)
        subscriber.on_event(self._config_refresh(runtime_config))
        subscriber.on_event(ListChangedNotifier(registry).on_invalidation)
        await subscriber.start()
        self._stack.push_async_callback(subscriber.stop)
        self._stack.callback(registry.close_streams)  # streams end with a result

        purger = TokenPurger(units, clock)  # expired grants must not linger
        purger.start()
        self._stack.callback(purger.stop)

        if settings.discovery_refresh_interval:  # 0 disables the periodic refresh
            refresher = ToolRefresher(
                discovery, ValkeyRefreshLock(redis), settings.discovery_refresh_interval
            )
            refresher.start()
            self._stack.callback(refresher.stop)

        # a rotated key is dropped once nothing stored needs it; no keys, nothing to move
        if cipher is not None and settings.token_reencryption_interval:
            reencryption = SecretReencryptionJob(
                SecretReencryption(units, cipher),
                ValkeyRefreshLock(redis),
                settings.token_reencryption_interval,
            )
            reencryption.start()
            self._stack.callback(reencryption.stop)

        # an invocation abandoned while waiting for client input still hears how it ended
        invocation_sweep = InvocationSweepJob(
            InvocationSweeper(paused_invocations, metering, clock), ValkeyRefreshLock(redis)
        )
        invocation_sweep.start()
        self._stack.callback(invocation_sweep.stop)

        # a session idle past session_lifetime is removed on one replica per interval
        session_sweep = SessionSweepJob(
            SessionSweeper(session_store, runtime_config, clock), ValkeyRefreshLock(redis)
        )
        session_sweep.start()
        self._stack.callback(session_sweep.stop)

        client_metadata = overrides.client_metadata_fetcher or HttpxClientMetadataFetcher(
            settings, redis
        )
        registration_policy = self._registration_policy()

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
            upstream_probe=upstream_probe,
            connection_diagnoser=diagnoser,
            delegated_tokens=delegated_tokens,
            audit=audit,
            runtime_config=runtime_config,
            counters=counters,
            profiles=profiles,
            rate_limiter=rate_limiter,
            auth_failure_limiter=auth_failure_limiter,
            auth_failure_guard=auth_failure_guard,
            token_cipher=cipher,
            upstream_tokens=upstream_tokens,
            upstream_connections=upstream_tokens or NoUpstreamConnections(),
            admin_sessions=AdminSessionStore(redis, max_age=settings.admin_session_lifetime),
            readiness=StoreReadinessProbe(sessions, redis, ShippedMigrations.read()),
            drain=drain,
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
            oidc_provider=self._start_oidc_provider(),
            invalidation=subscriber,
            mcp_router=mcp_router,
            client_metadata=client_metadata,
            # the grants this server serves, and how clients identify
            token_grants=(AuthorizationCodeGrant, RefreshTokenGrant),
            client_sources=(
                lambda uow: RegisteredClientSource(uow.oauth_clients),
                lambda uow: MetadataDocumentClientSource(
                    uow.oauth_clients,
                    client_metadata,
                    allowed_redirect_uris=registration_policy.allowed_redirect_uris,
                ),
            ),
            registration_policy=registration_policy,
        )

    def _registration_policy(self) -> RegistrationPolicy:
        """The redirect URIs and registration limits the operator configured."""
        return RegistrationPolicy(
            allowed_redirect_uris=RedirectUriAllowList.of(self._settings.dcr_allowed_redirect_uris),
            per_ip_limit=self._settings.dcr_rate_limit,
            per_ip_window=self._settings.dcr_rate_window,
            max_unused_clients=self._settings.dcr_max_unused_clients,
        )

    def _client_document_url(self) -> str | None:
        """The gateway's client metadata document, when an authorization server can fetch it.

        A client id must be an https URL, so a gateway served over plain http
        falls back to dynamic registration.
        """
        if not self._settings.public_base.startswith("https://"):
            return None
        return f"{self._settings.public_base}{UPSTREAM_CLIENT_DOCUMENT_PATH}"

    def _build_cipher(self) -> SecretCipher | None:
        # without keys nothing is stored, so upstream_oauth
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

    def _start_oidc_provider(self) -> OidcProvider | None:
        """The configured identity provider, discovering its issuer in the background.

        Startup does not wait for the issuer: an installer that creates the realm
        only once the gateway is ready would otherwise never see it ready.
        """
        # discovery is retried in the background, never awaited here
        if self._overrides.oidc_provider is not None:
            return self._overrides.oidc_provider
        provider = build_provider(self._settings)
        if provider is not None:
            provider.start()
            self._stack.callback(provider.stop)
        return provider

    @staticmethod
    def _config_refresh(runtime_config: RuntimeConfig):
        async def on_event(event) -> None:
            if event.entity_type == "config":
                await runtime_config.refresh()

        return on_event
