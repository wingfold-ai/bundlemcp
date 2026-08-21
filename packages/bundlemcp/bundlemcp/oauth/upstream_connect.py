"""Browser connect flow for upstream OAuth.

Mirrors the OIDC login flow: an authenticated admin (shared connection) or a
signed-in user (per_user) is redirected to the upstream's authorize endpoint;
the callback exchanges the code and stores the encrypted token.
"""

import json
import secrets
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from bundlemcp.models import IdentityMode, McpServer
from bundlemcp.oauth.authorize import PAGE_HEADERS, current_session_user
from bundlemcp.oauth.upstream_client import NeedsConnect

log = structlog.get_logger(__name__)

router = APIRouter(tags=["upstream-oauth"])

CONNECT_STATE_KEY = "bmcp:upstream-connect:{state}"
CONNECT_STATE_TTL = 600

_DONE_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Connected</title>"
    "<body style='font-family:system-ui;padding:2rem'>"
    "<h1>Connected</h1><p>{server} is now connected. You can close this window.</p>"
)


def _redirect_uri(request: Request) -> str:
    base = str(request.app.state.settings.public_url).rstrip("/")
    return f"{base}/oauth/upstream/callback"


async def _server(request: Request, name: str) -> McpServer:
    async with request.app.state.session_factory() as db:
        srv = (
            await db.execute(select(McpServer).where(McpServer.name == name))
        ).scalar_one_or_none()
    if srv is None:
        raise HTTPException(404, "server not found")
    return srv


@router.get("/oauth/upstream/{server_name}/connect", include_in_schema=False)
async def connect(server_name: str, request: Request, as_: str | None = Query(None, alias="as")):
    store = request.app.state.upstream_tokens
    if store is None:
        raise HTTPException(503, "upstream OAuth not configured (no encryption keys)")

    user = await current_session_user(request)
    if user is None:
        from urllib.parse import quote

        return RedirectResponse(f"/login?next={quote(str(request.url), safe='')}", status_code=302)

    server = await _server(request, server_name)
    per_user = as_ == "me"
    if per_user:
        # a per_user server must be per_user; the connecting user owns the token
        user_id: uuid.UUID | None = user.id
    else:
        # shared connection is an admin action (UPO-2/3)
        if not user.is_admin:
            raise HTTPException(403, "admin required to establish the shared connection")
        user_id = None
        if server.identity_mode == IdentityMode.PER_USER:
            raise HTTPException(
                400, "server is per_user; connect with ?as=me instead of a shared connection"
            )

    state = secrets.token_urlsafe(24)
    redirect_uri = _redirect_uri(request)
    try:
        url, verifier = await store.build_authorize(server, redirect_uri, state)
    except NeedsConnect:
        raise HTTPException(
            400, "server has no upstream OAuth client config (set client_id first)"
        ) from None
    await request.app.state.redis.set(
        CONNECT_STATE_KEY.format(state=state),
        json.dumps(
            {
                "server_id": str(server.id),
                "user_id": str(user_id) if user_id else None,
                "verifier": verifier,
                "redirect_uri": redirect_uri,
            }
        ),
        ex=CONNECT_STATE_TTL,
    )
    return RedirectResponse(url, status_code=302)


@router.get("/oauth/upstream/callback", include_in_schema=False)
async def callback(request: Request, code: str = "", state: str = ""):
    key = CONNECT_STATE_KEY.format(state=state)
    raw = await request.app.state.redis.get(key)
    await request.app.state.redis.delete(key)  # single-use (CSRF)
    if raw is None:
        raise HTTPException(400, "invalid or expired connect state")
    payload = json.loads(raw)

    store = request.app.state.upstream_tokens
    async with request.app.state.session_factory() as db:
        server = (
            await db.execute(
                select(McpServer).where(McpServer.id == uuid.UUID(payload["server_id"]))
            )
        ).scalar_one_or_none()
    if server is None:
        raise HTTPException(404, "server not found")

    user_id = uuid.UUID(payload["user_id"]) if payload["user_id"] else None
    await store.complete_authorize(
        server,
        user_id,
        code=code,
        code_verifier=payload["verifier"],
        redirect_uri=payload["redirect_uri"],
    )
    log.info("upstream_oauth.connected", server=server.name, per_user=user_id is not None)
    return HTMLResponse(_DONE_PAGE.format(server=server.name), headers=PAGE_HEADERS)
