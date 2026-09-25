"""Settling what an upstream's refusal means."""

from bundlemcp.application.contracts.upstream.upstream_oauth_provider import UpstreamOAuthProvider
from bundlemcp.application.discovery.connection_diagnosis import ConnectionDiagnosis
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect

NO_OAUTH_METADATA = "no_oauth_metadata"


class ConnectionDiagnoser:
    """Turns a probe failure into the connection state an operator acts on.

    The HTTP evidence decides most states on its own. A refusal is the
    exception: a server may challenge without naming its OAuth metadata and
    still publish it at a well-known location, so before a refusal is called
    ``credential_required`` the OAuth chain is followed. Evidence of OAuth is
    only ever a challenge or a document, never a 401 alone.
    """

    def __init__(self, oauth: UpstreamOAuthProvider | None) -> None:
        # oauth is None exactly when upstream OAuth is not available on this gateway
        self._oauth = oauth

    async def diagnose(self, server_url: str, failure: ProbeFailure) -> ConnectionDiagnosis:
        state = failure.state
        if self._oauth is None or state not in {
            ConnectionState.OAUTH_REQUIRED,
            ConnectionState.CREDENTIAL_REQUIRED,
        }:
            return ConnectionDiagnosis(state=state)
        try:
            meta = await self._oauth.discover(server_url)
        except NeedsConnect as exc:
            if exc.reason == NO_OAUTH_METADATA:
                return ConnectionDiagnosis(state=state)
            # the server points at OAuth metadata the gateway refuses to use
            return ConnectionDiagnosis(
                state=ConnectionState.OAUTH_REQUIRED, oauth_problem=exc.reason
            )
        return ConnectionDiagnosis(state=ConnectionState.OAUTH_REQUIRED, oauth=meta)
