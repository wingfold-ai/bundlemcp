"""CORS chosen by path: permissive on the MCP endpoints, allow-listed everywhere else.

Browser-based MCP clients run on origins the operator cannot list, so the MCP
endpoints reflect any ``Origin`` and expose the headers a client reads. That is
safe because they never allow credentials and never authenticate by cookie:
a caller presents a bearer token or an API key in a header. The management
API and the rest of the gateway keep the ``BUNDLEMCP_WEB_ORIGINS`` allow-list,
with credentials, for the admin UI's session cookie.
"""

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from bundlemcp.api.http.mcp_route_path import MCP_PATH

MCP_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]
MCP_REQUEST_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Mcp-Session-Id",
    "MCP-Protocol-Version",
    "Mcp-Method",
    "Last-Event-ID",
    "X-API-Key",
]
MCP_EXPOSED_HEADERS = ["Mcp-Session-Id", "WWW-Authenticate"]


class PathScopedCors:
    """Applies the MCP-endpoint CORS policy or the allow-list policy, by request path."""

    def __init__(self, app: ASGIApp, *, web_origins: list[str]) -> None:
        self._mcp = CORSMiddleware(
            app,
            allow_origin_regex=r".*",  # reflected, never "*", with Vary: Origin
            allow_credentials=False,
            allow_methods=MCP_METHODS,
            allow_headers=MCP_REQUEST_HEADERS,
            expose_headers=MCP_EXPOSED_HEADERS,
        )
        self._rest: ASGIApp = (
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
            await self._mcp(scope, receive, send)
        else:
            await self._rest(scope, receive, send)
