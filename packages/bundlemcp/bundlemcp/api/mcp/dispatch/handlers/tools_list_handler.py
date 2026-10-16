from typing import Any

import structlog
from fastapi import Response

from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.contracts.observability.gateway_metrics import GatewayMetrics
from bundlemcp.application.upstream_oauth.account_connect_prompts import AccountConnectPrompts
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.bundles.listed_tool import ListedTool
from bundlemcp.domain.servers.health_status import HealthStatus

log = structlog.get_logger(__name__)


class ToolsListHandler:
    """The curated, prefixed tool surface of the endpoint's bundle, in a stable order.

    A caller who still has to connect their own account to a member server
    also sees that server's connect-account tool, after the bundle's tools.

    The list is always served from the cache. When a member's health is
    ``error`` its cached tools may be out of date, so the listing is counted
    as degraded for that member and logged at WARN, never silently.
    """

    def __init__(
        self,
        cache_hints: CacheHints,
        connect_prompts: AccountConnectPrompts,
        metrics: GatewayMetrics,
    ) -> None:
        self._cache_hints = cache_hints
        self._connect_prompts = connect_prompts
        self._metrics = metrics

    @staticmethod
    def _entry(tool: ListedTool) -> dict[str, Any]:
        entry: dict[str, Any] = {"name": tool.presented_name, "inputSchema": tool.input_schema}
        if tool.title:
            entry["title"] = tool.title
        if tool.description:
            entry["description"] = tool.description
        if tool.annotations:
            entry["annotations"] = tool.annotations
        return entry

    def _note_degraded(self, view: BundleView) -> None:
        for server in view.servers.values():
            if server.health_status == HealthStatus.ERROR:
                self._metrics.tools_list_degraded(endpoint=view.endpoint.name, server=server.name)
                log.warning("tools_list.degraded", endpoint=view.endpoint.name, server=server.name)

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        self._note_degraded(ctx.view)
        tools: list[ListedTool] = list(ctx.view.tools)
        pending = await self._connect_prompts.pending(ctx.view, ctx.identity)
        result = {"tools": [self._entry(t) for t in tools + pending]}
        hint = await self._cache_hints.for_list()
        if pending:
            # a connect-account tool is this caller's alone, so no shared cache may keep the list
            hint = hint.model_copy(update={"scope": "private"})
        return rpc_result(message.id, ctx.shape(result, hint))
