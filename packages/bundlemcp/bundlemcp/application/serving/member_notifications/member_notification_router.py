"""Acting on what a member says outside any request: list changes, resource updates, logs."""

from collections.abc import Mapping
from typing import Any

import structlog
from pydantic import BaseModel

from bundlemcp.application.contracts.upstream.member_notification import MemberNotification
from bundlemcp.application.serving.member_notifications.member_notification_handler import (
    MemberNotificationHandler,
)
from bundlemcp.domain.servers.mcp_server import McpServer

log = structlog.get_logger(__name__)


class MemberNotificationRouter:
    """Takes a member's notification to the handler registered for its kind.

    Adding a kind of notification means registering a handler, not editing a
    dispatcher. A kind no handler is registered for is logged and dropped, so
    it never fails the upstream session's listener that heard it.
    """

    def __init__(self, handlers: Mapping[type[BaseModel], MemberNotificationHandler[Any]]) -> None:
        self._handlers = dict(handlers)

    async def received(
        self, server: McpServer, notification: MemberNotification, *, bound_to: str | None
    ) -> None:
        handler = self._handlers.get(type(notification))
        if handler is None:
            log.debug("member_notification.unhandled", server=server.name, kind=notification.kind)
            return
        await handler.handle(server, notification, bound_to=bound_to)
