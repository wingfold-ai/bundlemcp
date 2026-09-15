"""A modern client's change-notification stream, one long-lived POST at a time."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Response
from fastapi.responses import StreamingResponse
from mcp.shared.subscriptions import SUBSCRIPTION_ID_META_KEY
from mcp.types import INVALID_PARAMS, INVALID_REQUEST, SubscriptionFilter
from pydantic import ValidationError

from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.protocol.sse import (
    KEEPALIVE_SECONDS,
    SSE_HEADERS,
    SSE_KEEPALIVE,
    sse_data,
)
from bundlemcp.application.contracts.live_state.stream_registry import (
    STREAM_CLOSING,
    StreamRegistry,
)
from bundlemcp.application.serving.stream_key import StreamKey

# PROT-17: what the gateway can deliver between calls without a standing upstream
# connection (ADR-0012). Prompt/resource list changes and resource updates are
# not acknowledged, which the protocol defines as "not supported".
TOOLS_LIST_CHANGED = "notifications/tools/list_changed"


class SubscriptionsListenHandler:
    def __init__(self, registry: StreamRegistry) -> None:
        self._registry = registry

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        if message.id is None:
            return rpc_error(None, INVALID_REQUEST, "subscriptions/listen is a request", status=400)
        try:
            requested = SubscriptionFilter.model_validate(message.param("notifications", {}))
        except ValidationError as exc:
            return rpc_error(message.id, INVALID_PARAMS, f"invalid filter: {exc}", status=400)
        honoured = SubscriptionFilter(
            tools_list_changed=True if requested.tools_list_changed else None
        )
        key = StreamKey(
            endpoint_name=ctx.view.endpoint.name,
            bundle_name=ctx.view.bundle.name,
            stream_id=ctx.routing_key,
        )
        queue = self._registry.register_stream(key)
        return StreamingResponse(
            self._events(ctx, message.id, honoured, key, queue),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    async def _events(
        self,
        ctx: RequestContext,
        subscription_id: Any,
        honoured: SubscriptionFilter,
        key: StreamKey,
        queue: asyncio.Queue,
    ) -> AsyncIterator[str]:
        tag = {SUBSCRIPTION_ID_META_KEY: subscription_id}
        allowed = {TOOLS_LIST_CHANGED} if honoured.tools_list_changed else set()
        try:
            # The acknowledgement is always first and names only what will follow.
            yield sse_data(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/subscriptions/acknowledged",
                    "params": {
                        "_meta": tag,
                        "notifications": honoured.model_dump(by_alias=True, exclude_none=True),
                    },
                }
            )
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield SSE_KEEPALIVE
                    continue
                if payload is STREAM_CLOSING:
                    # Graceful closure: the response to the listen request itself.
                    yield sse_data(
                        {
                            "jsonrpc": "2.0",
                            "id": subscription_id,
                            "result": ctx.shape({"_meta": dict(tag)}),
                        }
                    )
                    return
                if payload.get("method") not in allowed:
                    continue
                params = dict(payload.get("params") or {})
                params["_meta"] = {**(params.get("_meta") or {}), **tag}
                yield sse_data({**payload, "params": params})
        finally:
            self._registry.unregister_stream(key, queue)
