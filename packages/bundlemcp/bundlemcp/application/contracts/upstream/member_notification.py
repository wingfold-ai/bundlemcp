"""What a member says outside any request, as the facts it states rather than the wire it used.

The pool translates each notification or listen event an upstream sends into
one of these, so nothing past the sink contract reads a JSON-RPC key. A
relayed notification is rebuilt from the fields here alone: whatever else the
member attached, such as its own ``_meta``, describes the member's hop to the
gateway and stops at the pool.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from bundlemcp.domain.sessions.log_levels import LogLevel

RESOURCE_UPDATED = "notifications/resources/updated"
LOG_MESSAGE = "notifications/message"


class ListedKind(StrEnum):
    """A list a member can announce a change of."""

    TOOLS = "tools"
    PROMPTS = "prompts"
    RESOURCES = "resources"


class MemberListChanged(BaseModel):
    """A member's tool, prompt or resource list changed."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["list_changed"] = Field(
        default="list_changed", description="Tells the notification kinds apart"
    )
    listed: ListedKind = Field(description="Which of the member's lists changed")


class MemberResourceUpdated(BaseModel):
    """A member resource changed and may need to be read again."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["resource_updated"] = Field(
        default="resource_updated", description="Tells the notification kinds apart"
    )
    uri: str = Field(
        min_length=1,
        description="The URI the member named, which may be a sub-resource of the one "
        "subscribed to",
    )

    def notification(self) -> dict[str, Any]:
        """The ``notifications/resources/updated`` relayed to a subscribed stream."""
        return {"jsonrpc": "2.0", "method": RESOURCE_UPDATED, "params": {"uri": self.uri}}


class MemberLogMessage(BaseModel):
    """A log message a member sent."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["log_message"] = Field(
        default="log_message", description="Tells the notification kinds apart"
    )
    level: LogLevel = Field(description="The message's severity, one of the eight MCP levels")
    logger: str | None = Field(
        default=None, description="The logger the member named; None when it named none"
    )
    data: JsonValue = Field(description="What was logged: a string or any JSON value")

    def notification(self) -> dict[str, Any]:
        """The ``notifications/message`` relayed to the client's stream."""
        params: dict[str, Any] = {"level": self.level, "data": self.data}
        if self.logger is not None:
            params["logger"] = self.logger
        return {"jsonrpc": "2.0", "method": LOG_MESSAGE, "params": params}


MemberNotification = Annotated[
    MemberListChanged | MemberResourceUpdated | MemberLogMessage,
    Field(discriminator="kind"),
]
