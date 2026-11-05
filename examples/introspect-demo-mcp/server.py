"""Demo MCP server that verifies every caller by introspecting its bearer at the gateway.

It stands in for an upstream that authenticates callers itself (RFC 7662), so the
integration suite can check what the gateway sends: the caller's forwarded bearer,
the static header discovery uses, the injected X-MCP-User and the mapped headers.
A request without a bearer the gateway reports active is refused with 401.

Environment:
  INTROSPECTION_URL            The gateway's introspection endpoint
                               (default http://gateway:8000/oauth/introspect).
  INTROSPECTION_CLIENT_ID      The client id sent with the service key (default bundlemcp).
  INTROSPECTION_CLIENT_SECRET  A gateway service key; introspection requires one.
"""

import json
import os

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

INTROSPECTION_URL = os.environ.get("INTROSPECTION_URL", "http://gateway:8000/oauth/introspect")
CLIENT_ID = os.environ.get("INTROSPECTION_CLIENT_ID", "bundlemcp")
CLIENT_SECRET = os.environ.get("INTROSPECTION_CLIENT_SECRET", "")

mcp = FastMCP("introspect-demo")


class IntrospectionGate:
    """Lets a request through only when the gateway reports its bearer active.

    The introspection result is kept on the request so a tool can report who
    the gateway said the caller is.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        result = await introspect(bearer_of(scope))
        if not result.get("active"):
            await refuse(send)
            return
        scope.setdefault("state", {})["introspection"] = result
        await self.app(scope, receive, send)


def bearer_of(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            return token.strip() if scheme.lower() == "bearer" and token.strip() else None
    return None


async def introspect(token: str | None) -> dict:
    if token is None:
        return {"active": False}
    async with httpx.AsyncClient(timeout=10) as client:
        reply = await client.post(
            INTROSPECTION_URL, data={"token": token}, auth=(CLIENT_ID, CLIENT_SECRET)
        )
    return reply.json() if reply.status_code == 200 else {"active": False}


async def refuse(send: Send) -> None:
    body = json.dumps({"error": "invalid_token"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer error="invalid_token"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


@mcp.tool
def whoami() -> dict:
    """Report who the gateway says the caller is, and which headers reached this server.

    Header values are not returned, except the identity header and the mapped
    tenant header; the bearer is reported only as present or absent.
    """
    request = get_http_request()
    introspection = request.state.introspection
    return {
        "sub": introspection.get("sub"),
        "client_id": introspection.get("client_id"),
        "token_use": introspection.get("token_use"),
        "signed_in_user": "oidc_sub" in introspection,
        "identity_header": request.headers.get("x-mcp-user"),
        "tenant": request.headers.get("x-tenant"),
        "bearer_present": "authorization" in request.headers,
        "header_names": sorted(request.headers.keys()),
    }


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",  # noqa: S104
        port=9000,
        path="/mcp",
        middleware=[Middleware(IntrospectionGate)],
        # fastmcp >= 3.4.3 rejects non-localhost Host headers unless allowed;
        # the gateway reaches this container by its compose service name.
        allowed_hosts=["introspect-demo", "introspect-demo:9000"],
    )
