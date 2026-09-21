"""Offering callers a way to connect the per-user upstream accounts they still lack."""

from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.upstream_oauth.connect_account_tool import ConnectAccountTool


class AccountConnectPrompts:
    """Decides which connect-account tools a caller sees, and what calling one returns.

    A caller sees one for each member server that needs their own upstream
    account and that they have not connected, or whose connection broke. An
    upstream tool that already presents the same name keeps it: the bundle's
    own tools are never shadowed.
    """

    def __init__(self, credentials: UpstreamCredentialResolver) -> None:
        self._credentials = credentials

    async def pending(self, view: BundleView, identity: CallerIdentity) -> list[ConnectAccountTool]:
        """The connect-account tools to list for this caller, in server-name order."""
        tools = []
        for tool in self._candidates(view):
            if await self._credentials.needs_account(tool.server, identity):
                tools.append(tool)
        return tools

    def resolve(self, view: BundleView, presented_name: str) -> ConnectAccountTool | None:
        """The connect-account tool a call names, whether or not it is listed right now.

        A caller who is already connected may still call it, to connect a
        different account.
        """
        return next((t for t in self._candidates(view) if t.presented_name == presented_name), None)

    def instructions(self, tool: ConnectAccountTool, identity: CallerIdentity) -> str:
        """What calling the tool tells the caller."""
        name = tool.server.name
        if identity.user_uuid is None:
            return (
                f"{name} needs each user to connect their own account, which requires "
                "signing in to this endpoint with OAuth rather than an API key."
            )
        return (
            f"Open this link in your browser to connect your {name} account:\n\n"
            f"{self._credentials.connect_url(tool.server)}\n\n"
            f"Once you have signed in, refresh the tool list (or reconnect this connector) "
            f"and {name}'s tools will be available."
        )

    @staticmethod
    def _candidates(view: BundleView) -> list[ConnectAccountTool]:
        taken = {t.presented_name for t in view.tools}
        candidates = [
            ConnectAccountTool.for_server(server)
            for _, server in sorted(view.servers.items())
            if server.requires_per_user_token
        ]
        return [t for t in candidates if t.presented_name not in taken]
