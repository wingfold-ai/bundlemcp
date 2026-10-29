"""Run the MCP python-sdk's "simple-auth" example as one OAuth-protected upstream.

The example ships two servers — an authorization server with a demo login form
and an MCP resource server that accepts only tokens that server issued — and
binds both to localhost with hard-coded URLs. This launcher supplies settings
instead: it serves both from one port on every interface, and registers the
one OAuth client the gateway presents, since the gateway works with a
pre-registered client rather than dynamic registration. The servers themselves
are the SDK's, untouched.

Environment:
  OAUTH_DEMO_PUBLIC_URL    The issuer, as both the gateway and the browser reach it
                           (default http://localhost:9000). The SDK allows plain http
                           only for localhost.
  OAUTH_DEMO_PORT          Listen port (default 9000).
  OAUTH_DEMO_CLIENT_ID     The client id the gateway is registered under (default bundlemcp).
  OAUTH_DEMO_REDIRECT_URIS Comma-separated redirect URIs of that client — the gateway's
                           /oauth/upstream/callback.
"""

import logging
import os

import uvicorn
from mcp.shared.auth import OAuthClientInformationFull
from mcp_simple_auth import auth_server
from mcp_simple_auth.auth_server import AuthServerSettings, create_authorization_server
from mcp_simple_auth.server import ResourceServerSettings, create_resource_server
from mcp_simple_auth.simple_auth_provider import SimpleAuthSettings
from pydantic import AnyHttpUrl, AnyUrl
from starlette.applications import Starlette
from starlette.routing import Mount

PORT = int(os.environ.get("OAUTH_DEMO_PORT", "9000"))
PUBLIC_URL = os.environ.get("OAUTH_DEMO_PUBLIC_URL", f"http://localhost:{PORT}").rstrip("/")
CLIENT_ID = os.environ.get("OAUTH_DEMO_CLIENT_ID", "bundlemcp")
REDIRECT_URIS = [u for u in os.environ.get("OAUTH_DEMO_REDIRECT_URIS", "").split(",") if u]

log = logging.getLogger("oauth-demo")


class SeededAuthProvider(auth_server.SimpleAuthProvider):
    """The example's provider with the gateway's client registered from the start."""

    def __init__(self, auth_settings: SimpleAuthSettings, auth_callback_path: str, url: str):
        super().__init__(auth_settings, auth_callback_path, url)
        self.clients[CLIENT_ID] = OAuthClientInformationFull(
            client_id=CLIENT_ID,
            client_name="bundlemcp gateway",
            redirect_uris=[AnyUrl(u) for u in REDIRECT_URIS],
            token_endpoint_auth_method="none",  # public client: PKCE, no secret  # noqa: S106
            grant_types=["authorization_code", "refresh_token"],
            scope=auth_settings.mcp_scope,
        )


# create_authorization_server() instantiates the provider by this module-level
# name, so binding the seeded subclass here is how the client gets registered
# without copying the example's wiring.
auth_server.SimpleAuthProvider = SeededAuthProvider


def build_app() -> Starlette:
    auth_settings = SimpleAuthSettings()
    authorization = create_authorization_server(
        AuthServerSettings(
            host="0.0.0.0",
            port=PORT,
            server_url=AnyHttpUrl(PUBLIC_URL),
            auth_callback_path=f"{PUBLIC_URL}/login",
        ),
        auth_settings,
    )
    resource = create_resource_server(
        ResourceServerSettings(
            host="0.0.0.0",
            port=PORT,
            server_url=AnyHttpUrl(f"{PUBLIC_URL}/mcp"),
            auth_server_url=AnyHttpUrl(PUBLIC_URL),
            # the example's verifier only trusts loopback or https for introspection
            auth_server_introspection_endpoint=f"http://127.0.0.1:{PORT}/introspect",
            mcp_scope=auth_settings.mcp_scope,
        )
    )
    resource_app = resource.streamable_http_app()
    # The authorization server's routes (/authorize, /token, /login, ...) and the
    # resource server (/mcp and its protected-resource document) share the port;
    # the resource server's session manager needs the lifespan the SDK's own app
    # would have run.
    return Starlette(
        routes=[*authorization.routes, Mount("/", app=resource_app)],
        lifespan=lambda app: resource.session_manager.run(),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not REDIRECT_URIS:
        log.warning("OAUTH_DEMO_REDIRECT_URIS is empty: no client can complete the flow")
    settings = SimpleAuthSettings()
    log.info(
        "oauth-demo: issuer %s, MCP at %s/mcp, client %s -> %s, demo login %s / %s",
        PUBLIC_URL,
        PUBLIC_URL,
        CLIENT_ID,
        REDIRECT_URIS,
        settings.demo_username,
        settings.demo_password,
    )
    uvicorn.run(build_app(), host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
