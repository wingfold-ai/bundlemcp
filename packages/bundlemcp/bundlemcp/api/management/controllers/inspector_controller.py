"""The MCP inspector: operations against an upstream, an endpoint, or an ad-hoc URL."""

from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter

from bundlemcp.api.http.management_auth import PrincipalProvider
from bundlemcp.api.http.providers import ClientIpProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import InspectorServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.api.mcp.protocol.sse import SSE_HEADERS
from bundlemcp.application.schemas import (
    InspectorCallEvent,
    InspectorCallRequest,
    InspectorConnection,
    InspectorPing,
    InspectorRequest,
    InspectorToolList,
)

CALL_EVENTS = TypeAdapter(InspectorCallEvent)
CALL_STREAM_DESCRIPTION = (
    "A Server-Sent Events stream. Each event's name is its payload's `type`: `progress` for "
    "every progress notification the target sends, as it arrives, then exactly one `result` "
    "(the call's outcome) or `failure` (the target gave no MCP answer), after which the stream "
    "ends."
)


class InspectorController(ManagementController):
    prefix = "/inspector"
    tags = ("inspector",)

    @route.post(":connect")
    async def connect(
        self,
        body: InspectorRequest,
        service: InspectorServiceProvider,
        principal: PrincipalProvider,
        caller_ip: ClientIpProvider,
    ) -> InspectorConnection:
        return await service.connect(body.target, principal, caller_ip)

    @route.post(":ping")
    async def ping(
        self,
        body: InspectorRequest,
        service: InspectorServiceProvider,
        principal: PrincipalProvider,
        caller_ip: ClientIpProvider,
    ) -> InspectorPing:
        return await service.ping(body.target, principal, caller_ip)

    @route.post(":list-tools")
    async def list_tools(
        self,
        body: InspectorRequest,
        service: InspectorServiceProvider,
        principal: PrincipalProvider,
        caller_ip: ClientIpProvider,
    ) -> InspectorToolList:
        return await service.list_tools(body.target, principal, caller_ip)

    @route.post(
        ":call-tool",
        response_class=StreamingResponse,
        responses={
            200: {
                "model": InspectorCallEvent,
                "description": CALL_STREAM_DESCRIPTION,
                "content": {"text/event-stream": {}},
            }
        },
    )
    async def call_tool(
        self,
        body: InspectorCallRequest,
        service: InspectorServiceProvider,
        principal: PrincipalProvider,
        caller_ip: ClientIpProvider,
    ) -> StreamingResponse:
        events = await service.call_tool(body, principal, caller_ip)
        return StreamingResponse(
            self._sse(events), media_type="text/event-stream", headers=SSE_HEADERS
        )

    @staticmethod
    async def _sse(events: AsyncIterator[InspectorCallEvent]) -> AsyncIterator[str]:
        async for event in events:
            yield f"event: {event.type}\ndata: {CALL_EVENTS.dump_json(event).decode()}\n\n"
