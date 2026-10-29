"""A modern client's change-notification stream, one long-lived POST at a time."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

import structlog
from fastapi import Response
from fastapi.responses import StreamingResponse
from mcp.shared.subscriptions import SUBSCRIPTION_ID_META_KEY
from mcp.types import INVALID_PARAMS, INVALID_REQUEST, SubscriptionFilter
from pydantic import ValidationError

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.protocol.sse import (
    KEEPALIVE_SECONDS,
    SSE_HEADERS,
    SSE_KEEPALIVE,
    sse_data,
)
from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscription,
)
from bundlemcp.application.contracts.live_state.stream_presence import StreamPresence
from bundlemcp.application.contracts.live_state.stream_registry import (
    STREAM_CLOSING,
    StreamRegistry,
)
from bundlemcp.application.contracts.upstream.member_notification import RESOURCE_UPDATED
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLease
from bundlemcp.application.serving.list_changed_notifier import (
    PROMPTS_LIST_CHANGED,
    RESOURCES_LIST_CHANGED,
    TOOLS_LIST_CHANGED,
)
from bundlemcp.application.serving.stream_key import StreamKey
from bundlemcp.domain.bundles.bundle_resource_uri import is_bundle_uri
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.server_capability import ServerCapability

log = structlog.get_logger(__name__)


class SubscriptionsListenHandler:
    """A modern client's change-notification stream, one long-lived POST at a time.

    List changes — the bundle's own and its members' — reach the stream as
    bundle invalidations. Each resource the filter names is subscribed to on
    every member that accepts subscriptions, over an upstream session
    dedicated to the stream and held until it closes; only the resources
    some member accepted are acknowledged.
    """

    def __init__(
        self, registry: StreamRegistry, presence: StreamPresence, fanout: MemberFanout
    ) -> None:
        self._registry = registry
        self._presence = presence
        self._fanout = fanout
        self._closing: set[asyncio.Task[None]] = set()

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        if message.id is None:
            return rpc_error(None, INVALID_REQUEST, "subscriptions/listen is a request", status=400)
        try:
            requested = SubscriptionFilter.model_validate(message.param("notifications", {}))
        except ValidationError as exc:
            return rpc_error(message.id, INVALID_PARAMS, f"invalid filter: {exc}", status=400)
        key = StreamKey(
            endpoint_name=ctx.view.endpoint.name,
            bundle_name=ctx.view.bundle.name,
            stream_id=ctx.routing_key,
        )
        queue = self._registry.register_stream(key)
        return StreamingResponse(
            self._events(ctx, message.id, requested, key, queue),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    async def _events(
        self,
        ctx: RequestContext,
        subscription_id: Any,
        requested: SubscriptionFilter,
        key: StreamKey,
        queue: asyncio.Queue,
    ) -> AsyncIterator[str]:
        watches = AsyncExitStack()
        try:
            watched = await self._watch(ctx, requested.resource_subscriptions or [], key, watches)
            honoured = SubscriptionFilter(
                tools_list_changed=True if requested.tools_list_changed else None,
                prompts_list_changed=True if requested.prompts_list_changed else None,
                resources_list_changed=True if requested.resources_list_changed else None,
                resource_subscriptions=watched or None,
            )
            async for event in self._stream(ctx, subscription_id, honoured, key, queue):
                yield event
        finally:
            self._registry.unregister_stream(key, queue)
            # a client closing the stream cancels this response, and would cancel
            # the upstream unsubscribes with it; they run on their own instead
            task = asyncio.create_task(self._close(key, watches))
            self._closing.add(task)
            task.add_done_callback(self._closing.discard)

    async def _close(self, key: StreamKey, watches: AsyncExitStack) -> None:
        try:
            await self._presence.release(key.stream_id)
            await self._fanout.leases.subscriptions.drop_stream(key.stream_id)
            await watches.aclose()
        except Exception:
            log.warning("listen.close_failed", exc_info=True)

    async def _watch(
        self, ctx: RequestContext, uris: list[str], key: StreamKey, watches: AsyncExitStack
    ) -> list[str]:
        """Subscribe to each member resource ``uris`` names, holding the sessions until the end."""
        uris = [uri for uri in uris if not is_bundle_uri(uri)]
        watched: list[str] = []
        if not uris:
            return watched
        for server in self._fanout.members(ctx, ServerCapability.RESOURCES):
            if not server.accepts_resource_subscriptions:
                continue
            # registered first so it runs last, once the lease has been given back
            leased: list[UpstreamLease] = []
            watches.push_async_callback(self._end, ctx, server, leased)
            try:
                lease = await watches.enter_async_context(
                    self._fanout.lease(ctx, server, dedicated_to=key.stream_id)
                )
            except Exception:
                log.info("listen.member_unavailable", server=server.name, exc_info=True)
                continue
            leased.append(lease)
            for uri in uris:
                try:
                    await lease.subscribe(uri)
                except Exception:
                    log.info("listen.subscribe_refused", server=server.name, exc_info=True)
                    continue
                watches.push_async_callback(self._unsubscribe, lease, uri)
                await self._fanout.leases.subscriptions.subscribe(
                    key.stream_id, ResourceSubscription(server_name=server.name, uri=uri)
                )
                if uri not in watched:
                    watched.append(uri)
        return watched

    @staticmethod
    async def _unsubscribe(lease: UpstreamLease, uri: str) -> None:
        try:
            await lease.unsubscribe(uri)
        except Exception:
            log.info("listen.unsubscribe_failed", exc_info=True)

    async def _end(
        self, ctx: RequestContext, server: McpServer, leased: list[UpstreamLease]
    ) -> None:
        """End the upstream session dedicated to a closed stream."""
        if not leased or leased[0].binding is None:
            return
        lease = leased[0]
        try:
            forwarded, credentials = await self._fanout.leases.headers(ctx, server)
            await self._fanout.leases.pool.end(server, lease.binding, {**forwarded, **credentials})
        except Exception:
            log.info("listen.end_failed", server=server.name, exc_info=True)

    async def _stream(
        self,
        ctx: RequestContext,
        subscription_id: Any,
        honoured: SubscriptionFilter,
        key: StreamKey,
        queue: asyncio.Queue,
    ) -> AsyncIterator[str]:
        tag = {SUBSCRIPTION_ID_META_KEY: subscription_id}
        allowed = {
            method
            for method, wanted in (
                (TOOLS_LIST_CHANGED, honoured.tools_list_changed),
                (PROMPTS_LIST_CHANGED, honoured.prompts_list_changed),
                (RESOURCES_LIST_CHANGED, honoured.resources_list_changed),
                (RESOURCE_UPDATED, honoured.resource_subscriptions),
            )
            if wanted
        }
        await self._presence.hold(key.stream_id)
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
                await self._presence.hold(key.stream_id)
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
