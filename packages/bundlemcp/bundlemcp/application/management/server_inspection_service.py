"""Finding out what an upstream is before it is registered."""

import asyncio
from urllib.parse import urlparse

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult, UpstreamProbe
from bundlemcp.application.discovery.connection_diagnoser import ConnectionDiagnoser
from bundlemcp.application.discovery.connection_diagnosis import ConnectionDiagnosis
from bundlemcp.application.schemas import (
    OAuthInspection,
    ServerInfoRead,
    ServerInspection,
    ServerInspectRequest,
    ServerUpsert,
)
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.internal_host import is_internal_host
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.servers.server_name_suggestion import suggest_server_name
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant

INSPECT_TIMEOUT_SECONDS = 20
MCP_PATH = "/mcp"
SSE_PATH = "/sse"
INSPECTION_SERVER_NAME = "inspection"  # never stored; names the transient probe target


_DETAIL = {
    ConnectionState.OAUTH_REQUIRED: "The server requires OAuth sign-in.",
    ConnectionState.CREDENTIAL_REQUIRED: "The server refused the request without a usable "
    "credential.",
    ConnectionState.INSUFFICIENT_SCOPE: "The credential lacks a permission the server needs.",
    ConnectionState.NOT_MCP: "The URL is not a Streamable HTTP MCP endpoint.",
    ConnectionState.UNREACHABLE: "The server could not be reached (connection, TLS or timeout).",
    ConnectionState.EGRESS_DENIED: "The gateway's egress policy does not allow this address.",
    ConnectionState.ERROR: "The server answered with an error.",
}


class ServerInspectionService:
    """Probes a URL the way discovery would, and reports what registering it takes.

    Nothing is stored. Candidate credential headers go to the upstream for
    this one probe and nowhere else. A URL that is not an MCP endpoint is
    retried once with ``/mcp`` appended, the most common slip.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        probe: UpstreamProbe,
        diagnoser: ConnectionDiagnoser,
        *,
        public_base: str,
    ) -> None:
        self._servers = uow.servers
        self._probe = probe
        self._diagnoser = diagnoser
        self._public_base = public_base

    @property
    def _callback_url(self) -> str:
        return f"{self._public_base}/oauth/upstream/callback"

    @property
    def _metadata_document_usable(self) -> bool:
        # an authorization server can only fetch the gateway's document over https
        return self._public_base.startswith("https://")

    async def inspect(self, body: ServerInspectRequest) -> ServerInspection:
        url = body.url
        outcome = await self._attempt(url, body.headers)
        suggested_url = None
        path = urlparse(url).path.rstrip("/")
        if (
            isinstance(outcome, ConnectionDiagnosis)
            and outcome.state == ConnectionState.NOT_MCP
            and not path.endswith((MCP_PATH, SSE_PATH))
        ):
            candidate = url.rstrip("/") + MCP_PATH
            retry = await self._attempt(candidate, body.headers)
            if not isinstance(retry, ConnectionDiagnosis) or retry.state != ConnectionState.NOT_MCP:
                url, outcome, suggested_url = candidate, retry, candidate
        if isinstance(outcome, ConnectionDiagnosis):
            return await self._refused(url, outcome, body, suggested_url)
        return await self._answered(url, outcome, body, suggested_url)

    async def _attempt(
        self, url: str, headers: dict[str, str]
    ) -> ProbeResult | ConnectionDiagnosis:
        target = McpServer(name=INSPECTION_SERVER_NAME, url=url, static_headers=headers)
        try:
            async with asyncio.timeout(INSPECT_TIMEOUT_SECONDS):
                return await self._probe.probe(target, {})
        except TimeoutError:
            return ConnectionDiagnosis(state=ConnectionState.UNREACHABLE)
        except ProbeFailure as failure:
            # only the classified state leaves this method, never the upstream's own
            # words, which may echo the probe's candidate headers
            return await self._diagnoser.diagnose(url, failure)

    async def _answered(
        self,
        url: str,
        seen: ProbeResult,
        body: ServerInspectRequest,
        suggested_url: str | None,
    ) -> ServerInspection:
        info = seen.server_info
        label = info.name if info is not None else None
        hints = []
        if suggested_url is not None:
            hints.append(f"The URL as given is not an MCP endpoint; {suggested_url} is.")
        if body.headers:
            hints.append("The server accepted the credential; save it as static headers.")
        return ServerInspection(
            url=url,
            connection_state=ConnectionState.READY,
            protocol_version=seen.protocol_version,
            server_info=ServerInfoRead(**info.model_dump()) if info is not None else None,
            tool_names=[tool.name for tool in seen.tools],
            suggested_url=suggested_url,
            hints=hints,
            suggestion=ServerUpsert(
                name=await self._free_name(label, url),
                description=(info.description or info.title) if info is not None else None,
                url=url,
                auth_mode=(ServerAuthMode.STATIC_HEADERS if body.headers else ServerAuthMode.NONE),
                send_identity_header=is_internal_host(url),
            ),
        )

    async def _refused(
        self,
        url: str,
        diagnosis: ConnectionDiagnosis,
        body: ServerInspectRequest,
        suggested_url: str | None,
    ) -> ServerInspection:
        state = diagnosis.state
        oauth = self._oauth(diagnosis) if state == ConnectionState.OAUTH_REQUIRED else None
        auth_mode = {
            ConnectionState.OAUTH_REQUIRED: ServerAuthMode.UPSTREAM_OAUTH,
            ConnectionState.CREDENTIAL_REQUIRED: ServerAuthMode.STATIC_HEADERS,
        }.get(state, ServerAuthMode.NONE)
        return ServerInspection(
            url=url,
            connection_state=state,
            detail=_DETAIL.get(state),
            oauth=oauth,
            suggested_url=suggested_url,
            hints=self._hints(url, state, oauth, bool(body.headers)),
            suggestion=ServerUpsert(
                name=await self._free_name(None, url),
                url=url,
                auth_mode=auth_mode,
                # a person's own account is the safe default for OAuth; shared is a choice
                identity_mode=(
                    IdentityMode.PER_USER
                    if auth_mode == ServerAuthMode.UPSTREAM_OAUTH
                    else IdentityMode.SHARED
                ),
                send_identity_header=is_internal_host(url),
            ),
        )

    def _oauth(self, diagnosis: ConnectionDiagnosis) -> OAuthInspection:
        meta = diagnosis.oauth
        if meta is None:
            return OAuthInspection(callback_url=self._callback_url, problem=diagnosis.oauth_problem)
        return OAuthInspection(
            issuer=meta.issuer,
            authorization_endpoint=meta.authorization_endpoint,
            scopes=meta.resource_scopes,
            client_identification=meta.automatic_identification(
                metadata_document_usable=self._metadata_document_usable
            ),
            supports_client_credentials=UpstreamGrant.CLIENT_CREDENTIALS.value
            in meta.grant_types_supported,
            callback_url=self._callback_url,
        )

    @staticmethod
    def _hints(
        url: str, state: ConnectionState, oauth: OAuthInspection | None, tried_headers: bool
    ) -> list[str]:
        if state == ConnectionState.OAUTH_REQUIRED and oauth is not None:
            if oauth.problem is not None:
                return [f"The server's OAuth metadata cannot be used: {oauth.problem}."]
            if oauth.client_identification == ClientIdentification.PREREGISTERED_REQUIRED:
                return [
                    "The authorization server offers no automatic client registration: "
                    f"register a client there with redirect URI {oauth.callback_url} and enter "
                    "its id (and secret) on the server's page after creating it."
                ]
            return ["Sign-in works automatically; choose whose account tool calls use."]
        if state == ConnectionState.CREDENTIAL_REQUIRED:
            if tried_headers:
                return ["The server refused the credential that was tried."]
            return [
                "The server refuses requests without a credential and publishes no OAuth "
                "metadata: it wants an API key or token header. Its documentation names the "
                "header, usually 'Authorization: Bearer <key>' or 'X-API-Key: <key>'."
            ]
        if state == ConnectionState.UNREACHABLE:
            return [
                "Check the URL and that the server is running. A server that is not up yet can "
                "still be registered: it is probed again on every tool refresh."
            ]
        if state == ConnectionState.EGRESS_DENIED:
            return [
                "The address is outside what the gateway may reach; an operator can allow it "
                "with BUNDLEMCP_EGRESS_ALLOW_CIDRS."
            ]
        if state == ConnectionState.NOT_MCP:
            if urlparse(url).path.rstrip("/").endswith(SSE_PATH):
                return [
                    "This looks like the retired HTTP+SSE transport, which the gateway does "
                    "not speak; run the server behind a Streamable HTTP sidecar."
                ]
            return ["The URL answers, but not as a Streamable HTTP MCP endpoint."]
        return []

    async def _free_name(self, label: str | None, url: str) -> str:
        """A suggested name no registered server has yet."""
        base = suggest_server_name(label, url)
        name, n = base, 2
        while await self._servers.by_name(name) is not None:
            name, n = f"{base}-{n}", n + 1
        return name
