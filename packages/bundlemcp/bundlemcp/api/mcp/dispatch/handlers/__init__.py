"""One class per JSON-RPC method the edge serves."""

from bundlemcp.api.mcp.dispatch.handlers.cancelled_notification_handler import (
    CancelledNotificationHandler,
)
from bundlemcp.api.mcp.dispatch.handlers.completion_handler import CompletionHandler
from bundlemcp.api.mcp.dispatch.handlers.initialize_handler import InitializeHandler
from bundlemcp.api.mcp.dispatch.handlers.logging_set_level_handler import (
    LoggingSetLevelHandler,
)
from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.dispatch.handlers.ping_handler import PingHandler
from bundlemcp.api.mcp.dispatch.handlers.prompts_get_handler import PromptsGetHandler
from bundlemcp.api.mcp.dispatch.handlers.prompts_list_handler import PromptsListHandler
from bundlemcp.api.mcp.dispatch.handlers.resource_templates_list_handler import (
    ResourceTemplatesListHandler,
)
from bundlemcp.api.mcp.dispatch.handlers.resources_list_handler import ResourcesListHandler
from bundlemcp.api.mcp.dispatch.handlers.resources_read_handler import ResourcesReadHandler
from bundlemcp.api.mcp.dispatch.handlers.resources_subscribe_handler import (
    ResourcesSubscribeHandler,
)
from bundlemcp.api.mcp.dispatch.handlers.resources_unsubscribe_handler import (
    ResourcesUnsubscribeHandler,
)
from bundlemcp.api.mcp.dispatch.handlers.server_discover_handler import (
    ServerDiscoverHandler,
)
from bundlemcp.api.mcp.dispatch.handlers.subscriptions_listen_handler import (
    SubscriptionsListenHandler,
)
from bundlemcp.api.mcp.dispatch.handlers.tools_list_handler import ToolsListHandler

__all__ = [
    "CancelledNotificationHandler",
    "CompletionHandler",
    "InitializeHandler",
    "LoggingSetLevelHandler",
    "MemberFanout",
    "PingHandler",
    "PromptsGetHandler",
    "PromptsListHandler",
    "ResourceTemplatesListHandler",
    "ResourcesListHandler",
    "ResourcesReadHandler",
    "ResourcesSubscribeHandler",
    "ResourcesUnsubscribeHandler",
    "ServerDiscoverHandler",
    "SubscriptionsListenHandler",
    "ToolsListHandler",
]
