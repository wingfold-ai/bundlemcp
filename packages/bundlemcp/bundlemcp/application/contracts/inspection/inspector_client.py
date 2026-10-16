from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class InspectedServer(BaseModel):
    """What a target said about itself when the inspector connected."""

    name: str | None = Field(default=None, description="Implementation name the server reports")
    title: str | None = Field(default=None, description="Display title, when the server sets one")
    version: str | None = Field(default=None, description="Implementation version")
    description: str | None = Field(
        default=None, description="What the server says it provides, when it says"
    )
    website_url: str | None = Field(default=None, description="Website, when the server sets one")
    protocol_version: str | None = Field(
        default=None, description="The MCP revision negotiated with the target"
    )
    capabilities: dict[str, Any] = Field(
        default_factory=dict, description="The capabilities the target advertised"
    )
    instructions: str | None = Field(
        default=None, description="The usage instructions the target sent, when it sent any"
    )


class InspectedCall(BaseModel):
    """How a tools/call ended: a result, or the JSON-RPC error the target answered with."""

    result: dict[str, Any] | None = Field(
        default=None, description="The CallToolResult as the target serialised it"
    )
    error_code: int | None = Field(default=None, description="JSON-RPC error code, on an error")
    error_message: str | None = Field(
        default=None, description="JSON-RPC error message, on an error"
    )


# progress, total, message — as the target's notifications/progress carries them
ProgressCallback = Callable[[float, float | None, str | None], Awaitable[None]]


@runtime_checkable
class InspectorClient(Protocol):
    """One open, initialised MCP connection to an inspector target."""

    @property
    def server(self) -> InspectedServer: ...

    async def ping(self) -> None: ...

    async def list_tools(self) -> list[dict[str, Any]]:
        """Every tool the target lists, each as its wire JSON (``inputSchema`` and all)."""
        ...

    async def call_tool(
        self, name: str, arguments: dict[str, Any], on_progress: ProgressCallback
    ) -> InspectedCall: ...
