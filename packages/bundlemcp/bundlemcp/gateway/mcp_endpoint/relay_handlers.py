"""Server-to-client requests relayed back down to the MCP client.

Each request goes out on the client's GET stream and its reply is awaited on a
correlation future, so the replica holding the stream answers it wherever the
call is running.
"""

import asyncio
import uuid

from fastmcp.client.elicitation import ElicitResult
from mcp.types import CreateMessageResult, Root

from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime


def build_relay_handlers(runtime: GatewayRuntime, session_id: str, wait_timeout: float) -> dict:
    """Elicitation/sampling handlers that forward to the downstream client.

    Only attached when the client advertised the capability (caller gates this).
    Each request is delivered on the client's GET stream and its reply awaited
    via a correlation future, bounded by the call's timeout.
    """

    async def _roundtrip(method: str, params: dict) -> dict:
        correlation_id = uuid.uuid4().hex
        future = runtime.registry.register_reply(correlation_id)
        request = {"jsonrpc": "2.0", "id": correlation_id, "method": method, "params": params}
        await runtime.signals.deliver(session_id, request)
        try:
            reply = await asyncio.wait_for(future, timeout=wait_timeout)
        finally:
            runtime.registry.unregister_reply(correlation_id)
        if "error" in reply:
            raise RuntimeError(reply["error"].get("message", "client rejected request"))
        return reply.get("result", {})

    async def elicitation_handler(message, response_type, params, context):
        payload = params.model_dump(by_alias=True, mode="json", exclude_none=True)
        result = await _roundtrip("elicitation/create", payload)
        return ElicitResult(action=result.get("action", "decline"), content=result.get("content"))

    async def sampling_handler(messages, params, context):
        payload = params.model_dump(by_alias=True, mode="json", exclude_none=True)
        result = await _roundtrip("sampling/createMessage", payload)
        return CreateMessageResult.model_validate(result)

    async def roots_handler(context):
        # PROT-4: relay the upstream's roots/list to the downstream client.
        result = await _roundtrip("roots/list", {})
        return [Root.model_validate(r) for r in result.get("roots", [])]

    async def log_handler(message):
        # PROT-7: forward an upstream log to the client's stream (notification).
        await runtime.signals.deliver(
            session_id,
            {
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": message.model_dump(by_alias=True, mode="json", exclude_none=True),
            },
        )

    return {
        "elicitation_handler": elicitation_handler,
        "sampling_handler": sampling_handler,
        "roots_handler": roots_handler,
        "log_handler": log_handler,
    }
