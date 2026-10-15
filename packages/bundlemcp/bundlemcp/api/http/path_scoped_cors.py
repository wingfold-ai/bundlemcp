"""CORS chosen by path: the allow-list everywhere except the MCP endpoints.

The management API and the rest of the gateway answer CORS from the
``BUNDLEMCP_WEB_ORIGINS`` allow-list, with credentials, for the admin UI's
session cookie. The MCP endpoints are passed through untouched: which browser
origins may use one is that endpoint's own setting, so the MCP edge answers
their CORS once it has looked the endpoint up.
"""

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from bundlemcp.api.http.mcp_route_path import MCP_PATH


class PathScopedCors:
    """Applies the allow-list CORS policy to every route but ``/{endpoint}/mcp``."""

    def __init__(self, app: ASGIApp, *, web_origins: list[str]) -> None:
        self._app = app
        self._allow_listed: ASGIApp = (
            CORSMiddleware(
                app,
                allow_origins=[origin.rstrip("/") for origin in web_origins],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
                expose_headers=["Mcp-Session-Id"],
            )
            if web_origins
            else app
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and MCP_PATH.match(scope.get("path", "")):
            await self._app(scope, receive, send)
        else:
            await self._allow_listed(scope, receive, send)
