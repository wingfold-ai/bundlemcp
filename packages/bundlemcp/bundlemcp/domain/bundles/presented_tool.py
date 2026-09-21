from pydantic import Field

from bundlemcp.domain.bundles.listed_tool import ListedTool
from bundlemcp.domain.servers.tool import Tool


class PresentedTool(ListedTool):
    """One upstream tool as an endpoint shows it, after curation and profile transforms.

    A call to it is forwarded to its server.
    """

    tool: Tool = Field(description="Cached upstream definition this was derived from")
