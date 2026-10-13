"""Gateway application factory: management API, probes; MCP endpoints mount here too."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import ConnectionError as StoreConnectionError
from redis.exceptions import TimeoutError as StoreTimeoutError

from bundlemcp.api.health.controllers.health_controller import HealthController
from bundlemcp.api.http.live_state_unavailable_handler import live_state_unavailable_handler
from bundlemcp.api.http.service_error_handler import service_error_handler
from bundlemcp.api.management.controllers import (
    ApiKeyController,
    AuditController,
    BundleController,
    BundlePromptController,
    BundleResourceController,
    ConfigController,
    EndpointController,
    MeController,
    ServerController,
    UserController,
)
from bundlemcp.api.mcp.controllers.mcp_endpoint_controller import McpEndpointController
from bundlemcp.api.oauth.controllers.authorize_controller import AuthorizeController
from bundlemcp.api.oauth.controllers.introspection_controller import IntrospectionController
from bundlemcp.api.oauth.controllers.login_controller import LoginController
from bundlemcp.api.oauth.controllers.metadata_controller import OAuthMetadataController
from bundlemcp.api.oauth.controllers.registration_controller import ClientRegistrationController
from bundlemcp.api.oauth.controllers.token_controller import OAuthTokenController
from bundlemcp.api.oauth.controllers.upstream_connect_controller import UpstreamConnectController
from bundlemcp.api.oauth.locked_out import LockedOut, locked_out_handler
from bundlemcp.api.oauth.oauth_error_response import (
    authorization_redirect_handler,
    oauth_error_handler,
)
from bundlemcp.application.errors import AuthorizationRedirectError, OAuthError, ServiceError
from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.config.settings import get_settings
from bundlemcp.infrastructure.config.structured_logging import configure_logging
from bundlemcp.main.composition_overrides import CompositionOverrides
from bundlemcp.main.composition_root import CompositionRoot

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None, *, overrides: CompositionOverrides | None = None
) -> FastAPI:
    settings = settings or get_settings()
    overrides = overrides or CompositionOverrides()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with CompositionRoot(app, settings, overrides):
            yield

    app = FastAPI(
        title="bundlemcp",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",  # API-3
        docs_url=f"{API_PREFIX}/docs",
    )
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(OAuthError, oauth_error_handler)
    app.add_exception_handler(AuthorizationRedirectError, authorization_redirect_handler)
    app.add_exception_handler(LockedOut, locked_out_handler)  # RATE-5
    # SES-14: Valkey still unreachable after the client's retries
    app.add_exception_handler(StoreConnectionError, live_state_unavailable_handler)
    app.add_exception_handler(StoreTimeoutError, live_state_unavailable_handler)

    if settings.web_origins:
        # SEC-4: credentials-enabled CORS for exactly the web app's origin(s)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.rstrip("/") for o in settings.web_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["Mcp-Session-Id"],
        )

    for controller in (
        ServerController(),
        BundleController(),
        BundlePromptController(),  # BPR-14
        BundleResourceController(),
        EndpointController(),
        ApiKeyController(),
        ConfigController(),
        AuditController(),
        MeController(),
    ):
        controller.mount(app, prefix=API_PREFIX)
    # OAuth server routes at root for .well-known discovery (spec 20)
    for controller in (
        OAuthMetadataController(),
        ClientRegistrationController(),
        AuthorizeController(),
        OAuthTokenController(),
        IntrospectionController(),
        LoginController(),
        UpstreamConnectController(),  # spec 23 connect flow
    ):
        controller.mount(app)
    UserController().mount(app, prefix=API_PREFIX)  # /api/v1/users (ADM-6, OAS-11)
    HealthController().mount(app)
    McpEndpointController().mount(app)  # public /{endpoint}/mcp (EP-1)
    return app
