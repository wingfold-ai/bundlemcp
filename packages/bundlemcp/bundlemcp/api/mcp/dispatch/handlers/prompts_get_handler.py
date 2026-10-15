from typing import Any

import structlog
from fastapi import Response
from mcp.types import INVALID_PARAMS

from bundlemcp.api.mcp.dispatch.handlers.input_required_bridge import (
    BridgedRead,
    InputRequiredBridge,
)
from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout, dump
from bundlemcp.api.mcp.protocol.bundle_content_wire import prompt_message
from bundlemcp.api.mcp.protocol.dialect import ProtocolEra
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.serving.bundle_content_reader import BundleContentReader
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.server_capability import ServerCapability
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect

log = structlog.get_logger(__name__)


class PromptsGetHandler:
    """Render a bundle prompt here, or strip the server prefix and forward to the owning
    member.

    A modern client's request goes through the input-required bridge, so a
    member that needs client input to render its prompt can ask for it.
    """

    def __init__(
        self, fanout: MemberFanout, content: BundleContentReader, bridge: InputRequiredBridge
    ) -> None:
        self._fanout = fanout
        self._content = content
        self._bridge = bridge

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        presented = message.param("name", "")
        parsed = PresentedName.parse(presented)  # split on the first `__`
        if parsed is None:
            # a name without `__` is the bundle's own; it never reaches a member
            return await self._bundle_prompt(ctx, message, presented)
        server = ctx.view.servers.get(parsed.server)
        # a member that never advertised prompts is not asked (ADR-0043)
        if server is None or not server.advertises(ServerCapability.PROMPTS):
            return rpc_error(message.id, INVALID_PARAMS, f"unknown prompt: {presented}")
        arguments = message.param("arguments")
        if ctx.era is ProtocolEra.STATELESS:
            return await self._bridge.serve(
                BridgedRead(
                    ctx,
                    message,
                    target=presented,
                    arguments=arguments or {},
                    members=[server],
                    read=lambda client, answers, upstream_state: client.session.get_prompt(
                        parsed.name,
                        _arguments(arguments) or None,
                        input_responses=answers,
                        request_state=upstream_state,
                        allow_input_required=True,
                    ),
                    render=lambda result: ctx.shape(dump(result)),
                    failed=self._failed,
                )
            )
        try:
            result = await self._fanout.call(
                ctx, server, lambda client: client.get_prompt_mcp(parsed.name, arguments)
            )
        except NeedsConnect:
            return rpc_error(message.id, -32000, self._fanout.credentials.connect_hint(server))
        except Exception as exc:
            log.warning("prompts.get_failed", server=server.name)
            return rpc_error(message.id, -32000, str(exc)[:200])
        return rpc_result(message.id, ctx.shape(dump(result)))

    def _failed(self, server: McpServer | None, exc: Exception | None) -> dict[str, Any]:
        if isinstance(exc, NeedsConnect) and server is not None:
            return {"code": -32000, "message": self._fanout.credentials.connect_hint(server)}
        log.warning("prompts.get_failed", server=server.name if server else None)
        return {"code": -32000, "message": str(exc)[:200] if exc else "prompt unavailable"}

    async def _bundle_prompt(
        self, ctx: RequestContext, message: JsonRpcMessage, name: str
    ) -> Response:
        listing = ctx.view.prompt(name)
        if listing is None:
            return rpc_error(message.id, INVALID_PARAMS, f"unknown prompt: {name}")
        supplied = _arguments(message.param("arguments"))
        if missing := listing.missing_arguments(supplied):
            return rpc_error(
                message.id, INVALID_PARAMS, f"missing required argument: {', '.join(missing)}"
            )
        rendered = await self._content.render_prompt(ctx.view.bundle.id, name, supplied)
        if rendered is None:  # deleted since the view was loaded
            return rpc_error(message.id, INVALID_PARAMS, f"unknown prompt: {name}")
        messages = [prompt_message(m, rendered.resources) for m in rendered.messages]
        result: dict[str, Any] = {"messages": [m for m in messages if m is not None]}
        if rendered.description:
            result["description"] = rendered.description
        return rpc_result(message.id, ctx.shape(result))


def _arguments(raw: Any) -> dict[str, str]:
    """The supplied arguments as text; anything that is not an object supplies none."""
    if not isinstance(raw, dict):
        return {}
    return {
        str(name): value if isinstance(value, str) else str(value) for name, value in raw.items()
    }
