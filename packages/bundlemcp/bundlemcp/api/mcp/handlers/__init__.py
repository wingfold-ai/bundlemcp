"""One class per JSON-RPC method the edge serves."""

from bundlemcp.api.mcp.handlers.cancelled_notification_handler import (
    CancelledNotificationHandler,
)
from bundlemcp.api.mcp.handlers.completion_handler import CompletionHandler
from bundlemcp.api.mcp.handlers.initialize_handler import (
    SESSION_HEADER,
    InitializeHandler,
)
from bundlemcp.api.mcp.handlers.logging_set_level_handler import (
    LoggingSetLevelHandler,
)
from bundlemcp.api.mcp.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.handlers.ping_handler import PingHandler
from bundlemcp.api.mcp.handlers.prompts_get_handler import PromptsGetHandler
from bundlemcp.api.mcp.handlers.prompts_list_handler import PromptsListHandler
from bundlemcp.api.mcp.handlers.resource_templates_list_handler import (
    ResourceTemplatesListHandler,
)
from bundlemcp.api.mcp.handlers.resources_list_handler import ResourcesListHandler
from bundlemcp.api.mcp.handlers.resources_read_handler import ResourcesReadHandler
from bundlemcp.api.mcp.handlers.resources_subscribe_handler import (
    ResourcesSubscribeHandler,
)
from bundlemcp.api.mcp.handlers.server_discover_handler import (
    ServerDiscoverHandler,
)
from bundlemcp.api.mcp.handlers.subscriptions_listen_handler import (
    SubscriptionsListenHandler,
)
from bundlemcp.api.mcp.handlers.tools_list_handler import ToolsListHandler

__all__ = [
    "SESSION_HEADER",
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
    "ServerDiscoverHandler",
    "SubscriptionsListenHandler",
    "ToolsListHandler",
]
