"""Gateway application factory: management API, probes; MCP endpoints mount here too."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.exceptions import ConnectionError as StoreConnectionError
from redis.exceptions import TimeoutError as StoreTimeoutError

from bundlemcp.api.health.controllers.health_controller import HealthController
from bundlemcp.api.http.live_state_unavailable_handler import live_state_unavailable_handler
from bundlemcp.api.http.path_scoped_cors import PathScopedCors
from bundlemcp.api.http.request_body_limit import (
    BodyTooLarge,
    RequestBodyLimit,
    body_too_large_handler,
)
from bundlemcp.api.http.service_error_handler import service_error_handler
from bundlemcp.api.http.store_unavailable_handler import store_unavailable_handler
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
from bundlemcp.api.mcp.protocol.server_info import SERVER_VERSION
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
from bundlemcp.application.contracts.persistence.store_unavailable import StoreUnavailable
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
        version=SERVER_VERSION,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
    )
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(OAuthError, oauth_error_handler)
    app.add_exception_handler(AuthorizationRedirectError, authorization_redirect_handler)
    app.add_exception_handler(LockedOut, locked_out_handler)
    # Valkey still unreachable after the client's retries
    app.add_exception_handler(StoreConnectionError, live_state_unavailable_handler)
    app.add_exception_handler(StoreTimeoutError, live_state_unavailable_handler)
    app.add_exception_handler(StoreUnavailable, store_unavailable_handler)
    app.add_exception_handler(BodyTooLarge, body_too_large_handler)
    # bounds request bodies before routing, parsing or admission
    app.add_middleware(RequestBodyLimit)

    # outermost, so every answer carries CORS, a 413 from the body limit included
    app.add_middleware(PathScopedCors, web_origins=settings.web_origins)

    for controller in (
        ServerController(),
        BundleController(),
        BundlePromptController(),
        BundleResourceController(),
        EndpointController(),
        ApiKeyController(),
        ConfigController(),
        AuditController(),
        MeController(),
    ):
        controller.mount(app, prefix=API_PREFIX)
    # OAuth server routes at root for .well-known discovery (the auth spec)
    for controller in (
        OAuthMetadataController(),
        ClientRegistrationController(),
        AuthorizeController(),
        OAuthTokenController(),
        IntrospectionController(),
        LoginController(),
        UpstreamConnectController(),  # the upstreams spec connect flow
    ):
        controller.mount(app)
    UserController().mount(app, prefix=API_PREFIX)  # /api/v1/users
    HealthController().mount(app)
    McpEndpointController().mount(app)  # public /{endpoint}/mcp
    return app
