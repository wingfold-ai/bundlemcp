from dataclasses import dataclass
from typing import Any

from bundlemcp.models import McpServer, Tool


@dataclass
class PresentedTool:
    presented_name: str
    server: McpServer
    tool: Tool
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    annotations: dict[str, Any] | None
