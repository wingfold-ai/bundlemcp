"""The tool that stands in for a per-user server's tools until the caller connects."""

from bundlemcp.domain.bundles.listed_tool import ListedTool
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.mcp_server import McpServer

CONNECT_ACCOUNT_TOOL = "connect_account"  # UPS-27: presented as `<server>__connect_account`


class ConnectAccountTool(ListedTool):
    """A gateway-provided tool that hands the caller the link to connect their account.

    A server whose tools need each user's own upstream account offers nothing
    to a user who has not connected one, and without a tool to call they would
    never be told how. This tool is that way in: it is listed only to callers
    who still have to connect, and calling it reaches no upstream.
    """

    @classmethod
    def for_server(cls, server: McpServer) -> "ConnectAccountTool":
        title = f"Connect your {server.name} account"
        return cls(
            presented_name=PresentedName(server=server.name, name=CONNECT_ACCOUNT_TOOL).text,
            server=server,
            title=title,
            description=(
                f"Sign in to {server.name} so its tools become available. "
                "Returns a link to open in your browser."
            ),
            input_schema={"type": "object", "properties": {}},
            annotations={"title": title, "readOnlyHint": True, "openWorldHint": False},
        )
