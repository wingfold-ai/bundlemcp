"""The SDK's notifications and listen events, as the member notifications the sink takes.

Each SDK type a member can speak in maps to one converter. A type not in the
tables is not a member notification the gateway acts on, and one whose fields
do not validate (an empty URI, a level outside the eight) is dropped here, so
nothing past the pool sees it.
"""

from collections.abc import Callable
from typing import Any

import structlog
from mcp import types as mcp_types
from mcp.shared.subscriptions import (
    PromptsListChanged,
    ResourcesListChanged,
    ResourceUpdated,
    ServerEvent,
    ToolsListChanged,
)
from pydantic import ValidationError

from bundlemcp.application.contracts.upstream.member_notification import (
    ListedKind,
    MemberListChanged,
    MemberLogMessage,
    MemberNotification,
    MemberResourceUpdated,
)

log = structlog.get_logger(__name__)

_SERVER_NOTIFICATIONS: dict[type, Callable[[Any], MemberNotification]] = {
    mcp_types.ToolListChangedNotification: lambda _: MemberListChanged(listed=ListedKind.TOOLS),
    mcp_types.PromptListChangedNotification: lambda _: MemberListChanged(listed=ListedKind.PROMPTS),
    mcp_types.ResourceListChangedNotification: lambda _: MemberListChanged(
        listed=ListedKind.RESOURCES
    ),
    mcp_types.ResourceUpdatedNotification: lambda message: MemberResourceUpdated(
        uri=str(message.params.uri)
    ),
}

_LISTEN_EVENTS: dict[type, Callable[[Any], MemberNotification]] = {
    ToolsListChanged: lambda _: MemberListChanged(listed=ListedKind.TOOLS),
    PromptsListChanged: lambda _: MemberListChanged(listed=ListedKind.PROMPTS),
    ResourcesListChanged: lambda _: MemberListChanged(listed=ListedKind.RESOURCES),
    ResourceUpdated: lambda event: MemberResourceUpdated(uri=event.uri),
}


def from_server_notification(message: object) -> MemberNotification | None:
    """The member notification a handshake-era session's message states; None for any other.

    Log messages are not among them: the SDK hands those to the log handler,
    which translates them with ``from_log_message``.
    """
    return _translate(_SERVER_NOTIFICATIONS, message)


def from_listen_event(event: ServerEvent) -> MemberNotification | None:
    """The member notification an event on a modern member's listen stream states."""
    return _translate(_LISTEN_EVENTS, event)


def from_log_message(params: mcp_types.LoggingMessageNotificationParams) -> MemberLogMessage | None:
    """The log message a member sent, without anything else it attached."""
    try:
        return MemberLogMessage(level=params.level, logger=params.logger, data=params.data)
    except ValidationError:
        log.debug("member_notification.malformed", sdk_type="LoggingMessageNotification")
        return None


def _translate(
    table: dict[type, Callable[[Any], MemberNotification]], message: object
) -> MemberNotification | None:
    converter = table.get(type(message))
    if converter is None:
        log.debug("member_notification.ignored", sdk_type=type(message).__name__)
        return None
    try:
        return converter(message)
    except ValidationError:
        log.debug("member_notification.malformed", sdk_type=type(message).__name__)
        return None
