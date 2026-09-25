"""Browser connect flow for upstream OAuth.

Mirrors the OIDC login flow: an authenticated admin (shared connection) or a
signed-in user (per_user) is redirected to the upstream's authorize endpoint;
the callback exchanges the code, stores the encrypted token, and has the
server's tools discovered with it.
"""

import secrets
from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.providers import SettingsProvider, UnitOfWorkProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.oauth.browser_state.upstream_connect_state import UpstreamConnectState
from bundlemcp.api.oauth.pages.page_headers import PAGE_HEADERS
from bundlemcp.api.oauth.pages.page_templates import PAGE_TEMPLATES
from bundlemcp.api.oauth.providers import (
    ConnectStatesProvider,
    CurrentSessionUserProvider,
    DiscoveryProvider,
    UpstreamTokensProvider,
)
from bundlemcp.application.settings.settings import Settings
from bundlemcp.application.upstream_oauth.upstream_connect_flow import CLIENT_NAME
from bundlemcp.domain.oauth.application_type import ApplicationType
from bundlemcp.domain.oauth.client_id_metadata_document import ClientIdMetadataDocument
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect

log = structlog.get_logger(__name__)


class UpstreamConnectController(Controller):
    prefix = "/oauth/upstream"
    tags = ("upstream-oauth",)
    include_in_schema = False

    @staticmethod
    def _redirect_uri(settings: Settings) -> str:
        return f"{settings.public_base}/oauth/upstream/callback"

    @route.get("/client.json")
    async def client_document(self, settings: SettingsProvider) -> Response:
        """The gateway's own OAuth client metadata document (UPO-1, CIMD).

        An upstream authorization server that accepts metadata-document client
        ids fetches this URL, which is also the client id the gateway presents.
        """
        document = ClientIdMetadataDocument(
            client_id=f"{settings.public_base}/oauth/upstream/client.json",
            client_name=CLIENT_NAME,
            client_uri=settings.public_base,
            redirect_uris=[self._redirect_uri(settings)],
            application_type=ApplicationType.WEB,
        )
        return JSONResponse(
            document.model_dump(mode="json", exclude_none=True),
            headers={"Cache-Control": "public, max-age=3600"},
        )

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
        server = await uow.servers.by_name(server_name)
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
        except NeedsConnect as exc:
            if exc.reason == "no_client_config":
                detail = (
                    "server has no upstream OAuth client config and its authorization server "
                    "offers neither client metadata documents nor dynamic registration "
                    "(set client_id first)"
                )
            elif exc.reason == "client_credentials_client":
                detail = (
                    "the server's client uses client credentials; connect it with "
                    "POST /api/v1/servers/{name}/upstream-oauth:connect instead"
                )
            else:
                detail = f"upstream authorization server unavailable: {exc.reason}"
            raise HTTPException(400, detail) from None
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
        discovery: DiscoveryProvider,
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
        server = await uow.servers.get(pending.server_id)
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
        # DISC-1: the new token may be the first that can list the server's tools, and
        # the connecting user's tool list changes either way, so their bundles re-list
        await discovery.schedule_probe(server.id, announce=True)
        html = PAGE_TEMPLATES.get_template("connected.html").render(server_name=server.name)
        return HTMLResponse(html, headers=PAGE_HEADERS)
