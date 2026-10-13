from typing import Any

import structlog
from fastapi import Response
from mcp.types import INVALID_PARAMS

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout, dump
from bundlemcp.api.mcp.protocol.bundle_content_wire import prompt_message
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.serving.bundle_content_reader import BundleContentReader
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.server_capability import ServerCapability
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect

log = structlog.get_logger(__name__)


class PromptsGetHandler:
    """Render a bundle prompt here, or strip the server prefix and forward to the owning
    member."""

    def __init__(self, fanout: MemberFanout, content: BundleContentReader) -> None:
        self._fanout = fanout
        self._content = content

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        presented = message.param("name", "")
        parsed = PresentedName.parse(presented)  # BND-2 first-`__`
        if parsed is None:
            # BND-26: a name without `__` is the bundle's own; it never reaches a member
            return await self._bundle_prompt(ctx, message, presented)
        server = ctx.view.servers.get(parsed.server)
        # BND-8: a member that never advertised prompts is not asked (ADR-0043)
        if server is None or not server.advertises(ServerCapability.PROMPTS):
            return rpc_error(message.id, INVALID_PARAMS, f"unknown prompt: {presented}")
        arguments = message.param("arguments")
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

    async def _bundle_prompt(
        self, ctx: RequestContext, message: JsonRpcMessage, name: str
    ) -> Response:
        listing = ctx.view.prompt(name)
        if listing is None:
            return rpc_error(message.id, INVALID_PARAMS, f"unknown prompt: {name}")
        supplied = _arguments(message.param("arguments"))
        if missing := listing.missing_arguments(supplied):  # BND-21
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
