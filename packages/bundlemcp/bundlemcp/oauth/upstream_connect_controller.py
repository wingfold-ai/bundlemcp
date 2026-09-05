"""Browser connect flow for upstream OAuth.

Mirrors the OIDC login flow: an authenticated admin (shared connection) or a
signed-in user (per_user) is redirected to the upstream's authorize endpoint;
the callback exchanges the code and stores the encrypted token.
"""

import secrets
from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from bundlemcp.http import Controller, route
from bundlemcp.models import McpServer
from bundlemcp.oauth.page_headers import PAGE_HEADERS
from bundlemcp.oauth.providers import (
    ConnectStatesProvider,
    CurrentSessionUserProvider,
    UpstreamTokensProvider,
)
from bundlemcp.oauth.upstream_client import NeedsConnect
from bundlemcp.oauth.upstream_connect_state import UpstreamConnectState
from bundlemcp.providers import SettingsProvider, UnitOfWorkProvider
from bundlemcp.settings import Settings
from bundlemcp.store import Repository

log = structlog.get_logger(__name__)

_DONE_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Connected</title>"
    "<body style='font-family:system-ui;padding:2rem'>"
    "<h1>Connected</h1><p>{server} is now connected. You can close this window.</p>"
)


class UpstreamConnectController(Controller):
    prefix = "/oauth/upstream"
    tags = ("upstream-oauth",)
    include_in_schema = False

    @staticmethod
    def _redirect_uri(settings: Settings) -> str:
        return f"{settings.public_base}/oauth/upstream/callback"

    @route.get("/{server_name}/connect")
    async def connect(
        self,
        server_name: str,
        request: Request,
        uow: UnitOfWorkProvider,
        settings: SettingsProvider,
        states: ConnectStatesProvider,
        store: UpstreamTokensProvider,
        user: CurrentSessionUserProvider,
        as_: Annotated[str | None, Query(alias="as")] = None,
    ) -> Response:
        if store is None:
            raise HTTPException(503, "upstream OAuth not configured (no encryption keys)")
        if user is None:
            return RedirectResponse(
                f"/login?next={quote(str(request.url), safe='')}", status_code=302
            )
        server = await Repository(uow.session, McpServer).by_name(server_name)
        if server is None:
            raise HTTPException(404, "server not found")

        if as_ == "me":
            user_id = user.id  # the connecting user owns the token
        else:
            # a shared connection is an admin action (UPO-2/3)
            if not user.is_admin:
                raise HTTPException(403, "admin required to establish the shared connection")
            if server.is_per_user:
                raise HTTPException(
                    400, "server is per_user; connect with ?as=me instead of a shared connection"
                )
            user_id = None

        redirect_uri = self._redirect_uri(settings)
        state = secrets.token_urlsafe(24)  # the upstream echoes it back; it retrieves our record
        try:
            start = await store.build_authorize(server, redirect_uri, state)
        except NeedsConnect:
            raise HTTPException(
                400, "server has no upstream OAuth client config (set client_id first)"
            ) from None
        await states.put(
            UpstreamConnectState(
                server_id=server.id,
                user_id=user_id,
                code_verifier=start.code_verifier,
                redirect_uri=redirect_uri,
                issuer=start.issuer,
                iss_required=start.iss_required,
            ),
            token=state,
        )
        return RedirectResponse(start.url, status_code=302)

    @route.get("/callback")
    async def callback(
        self,
        uow: UnitOfWorkProvider,
        states: ConnectStatesProvider,
        store: UpstreamTokensProvider,
        code: str = "",
        state: str = "",
        iss: str = "",
        error: str = "",
        error_description: str = "",
    ) -> Response:
        if store is None:
            raise HTTPException(503, "upstream OAuth not configured (no encryption keys)")
        pending = await states.take(state)  # single-use (CSRF)
        if pending is None:
            raise HTTPException(400, "invalid or expired connect state")
        # UPO-8 (RFC 9207 section 2.4): checked before the code is redeemed and
        # before any error the response carries is acted on.
        if iss:
            if pending.issuer is None or iss != pending.issuer:
                raise HTTPException(400, "authorization server issuer mismatch")
        elif pending.iss_required:
            raise HTTPException(400, "authorization response lacks the iss the server advertises")
        if error:
            raise HTTPException(
                400, f"upstream authorization failed: {error} {error_description}".strip()
            )
        server = await Repository(uow.session, McpServer).get(pending.server_id)
        if server is None:
            raise HTTPException(404, "server not found")
        await store.complete_authorize(
            server,
            pending.user_id,
            code=code,
            code_verifier=pending.code_verifier,
            redirect_uri=pending.redirect_uri,
        )
        log.info(
            "upstream_oauth.connected", server=server.name, per_user=pending.user_id is not None
        )
        return HTMLResponse(_DONE_PAGE.format(server=server.name), headers=PAGE_HEADERS)
