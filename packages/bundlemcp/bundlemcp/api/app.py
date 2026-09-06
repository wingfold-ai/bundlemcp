"""Gateway application factory: management API, probes; MCP endpoints mount here too."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bundlemcp.api.composition import CompositionRoot
from bundlemcp.api.composition_overrides import CompositionOverrides
from bundlemcp.api.controllers import (
    ApiKeyController,
    AuditController,
    BundleController,
    ConfigController,
    EndpointController,
    HealthController,
    MeController,
    ServerController,
    UserController,
)
from bundlemcp.api.errors import service_error_handler
from bundlemcp.gateway.mcp_endpoint import McpEndpointController
from bundlemcp.oauth.authorize_controller import AuthorizeController
from bundlemcp.oauth.metadata_controller import OAuthMetadataController
from bundlemcp.oauth.oauth_error_response import (
    authorization_redirect_handler,
    oauth_error_handler,
)
from bundlemcp.oauth.oidc.login_controller import LoginController
from bundlemcp.oauth.registration_controller import ClientRegistrationController
from bundlemcp.oauth.token_controller import OAuthTokenController
from bundlemcp.oauth.upstream_connect_controller import UpstreamConnectController
from bundlemcp.services.errors import AuthorizationRedirectError, OAuthError, ServiceError
from bundlemcp.settings import Settings, get_settings
from bundlemcp.structured_logging import configure_logging

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
        LoginController(),
        UpstreamConnectController(),  # spec 23 connect flow
    ):
        controller.mount(app)
    UserController().mount(app, prefix=API_PREFIX)  # /api/v1/users (ADM-6, OAS-11)
    HealthController().mount(app)
    McpEndpointController().mount(app)  # public /{endpoint}/mcp (EP-1)
    return app
