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
from bundlemcp.oauth import authorize as oauth_authorize
from bundlemcp.oauth import metadata as oauth_metadata
from bundlemcp.oauth import registration as oauth_registration
from bundlemcp.oauth import token as oauth_token
from bundlemcp.oauth import upstream_connect as oauth_upstream_connect
from bundlemcp.oauth.oidc import routes as oauth_oidc
from bundlemcp.services.errors import ServiceError
from bundlemcp.settings import Settings, get_settings

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None, *, overrides: CompositionOverrides | None = None
) -> FastAPI:
    settings = settings or get_settings()
    overrides = overrides or CompositionOverrides()

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
    for router in (
        oauth_metadata.router,
        oauth_registration.router,
        oauth_authorize.router,
        oauth_token.router,
        oauth_oidc.router,
        oauth_upstream_connect.router,  # spec 23 connect flow
    ):
        app.include_router(router)
    UserController().mount(app, prefix=API_PREFIX)  # /api/v1/users (ADM-6, OAS-11)
    HealthController().mount(app)
    McpEndpointController().mount(app)  # public /{endpoint}/mcp (EP-1)
    return app
