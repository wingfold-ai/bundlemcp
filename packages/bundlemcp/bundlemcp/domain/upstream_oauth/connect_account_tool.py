"""The tool that stands in for a per-user server's tools until the caller connects."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.mcp_server import McpServer

CONNECT_ACCOUNT_TOOL = "connect_account"  # UPO-3: presented as `<server>__connect_account`


class ConnectAccountTool(BaseModel):
    """A gateway-provided tool that hands the caller the link to connect their account.

    A server whose tools need each user's own upstream account offers nothing
    to a user who has not connected one, and without a tool to call they would
    never be told how. This tool is that way in: it is listed only to callers
    who still have to connect, and calling it reaches no upstream.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    server: McpServer = Field(description="Member server the caller has to connect an account to")

    @property
    def presented_name(self) -> str:
        return PresentedName(server=self.server.name, name=CONNECT_ACCOUNT_TOOL).text

    @property
    def title(self) -> str:
        return f"Connect your {self.server.name} account"

    @property
    def description(self) -> str:
        return (
            f"Sign in to {self.server.name} so its tools become available. "
            "Returns a link to open in your browser."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def annotations(self) -> dict[str, Any]:
        return {"title": self.title, "readOnlyHint": True, "openWorldHint": False}
