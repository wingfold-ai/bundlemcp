"""Demo MCP server that reports what it learns about its caller.

It stands in for an upstream that verifies the gateway's forwarded bearer: every
request needs a bearer, either the fixed discovery token the gateway's static
header carries, or a token the gateway's RFC 7662 introspection reports active.
The ``whoami`` tool returns the identity it resolved and the identity headers it
received, never a credential value.
"""

import hmac
import os
from typing import Any

import httpx
import uvicorn
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

DISCOVERY_TOKEN = os.environ["DISCOVERY_TOKEN"]
INTROSPECTION_URL = os.environ["INTROSPECTION_URL"]
INTROSPECTION_AUTH = (
    os.environ.get("INTROSPECTION_CLIENT_ID", "bundlemcp"),
    os.environ["INTROSPECTION_CLIENT_SECRET"],
)
DISCOVERY_CALLER = "discovery"

mcp = FastMCP("identity-demo")


def _bearer(authorization: str | None) -> str | None:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


async def _identify(token: str | None) -> dict[str, Any] | None:
    """The caller a bearer stands for, or None when it is missing or not active."""
    if token is None:
        return None
    if hmac.compare_digest(token.encode(), DISCOVERY_TOKEN.encode()):
        return {"active": True, "sub": DISCOVERY_CALLER}
    async with httpx.AsyncClient(timeout=10) as client:
        reply = await client.post(INTROSPECTION_URL, data={"token": token}, auth=INTROSPECTION_AUTH)
    if reply.status_code != 200:
        return None
    claims = reply.json()
    return claims if claims.get("active") is True else None


class RequireCaller:
    """Answer 401 to any request whose bearer does not identify a caller."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            try:
                caller = await _identify(_bearer(headers.get("authorization")))
            except httpx.HTTPError:
                # introspection is down: say so, rather than calling the bearer invalid
                await _reply(send, 503)
                return
            if caller is None:
                # a bare 401: no OAuth metadata, so the gateway does not treat
                # this server as one it must sign in to
                await _reply(send, 401)
                return
        await self._app(scope, receive, send)


async def _reply(send: Send, status: int) -> None:
    await send({"type": "http.response.start", "status": status, "headers": []})
    await send({"type": "http.response.body", "body": b""})


@mcp.tool
async def whoami() -> dict[str, Any]:
    """Report the caller this server resolved and the identity headers it received."""
    headers = get_http_headers(include_all=True)
    claims = await _identify(_bearer(headers.get("authorization"))) or {}
    return {
        "caller": claims.get("sub"),
        "client_id": claims.get("client_id"),
        "has_oidc_subject": "oidc_iss" in claims and "oidc_sub" in claims,
        "x_mcp_user": headers.get("x-mcp-user"),
        "tenant": headers.get("x-tenant"),
        "header_names": sorted(headers),
    }


if __name__ == "__main__":
    app = mcp.http_app(
        path="/mcp",
        middleware=[Middleware(RequireCaller)],
        # the gateway reaches this container by its compose service name
        allowed_hosts=["identity-demo", "identity-demo:9000", "localhost:9000", "127.0.0.1:9000"],
    )
    uvicorn.run(app, host="0.0.0.0", port=9000)  # noqa: S104
