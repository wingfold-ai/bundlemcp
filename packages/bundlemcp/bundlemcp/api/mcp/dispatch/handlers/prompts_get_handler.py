import structlog
from fastapi import Response

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout, dump
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect

log = structlog.get_logger(__name__)


class PromptsGetHandler:
    """Strip the server prefix and forward to the owning member."""

    def __init__(self, fanout: MemberFanout) -> None:
        self._fanout = fanout

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        presented = message.param("name", "")
        parsed = PresentedName.parse(presented)  # BND-2 first-`__`
        server = ctx.view.servers.get(parsed.server) if parsed else None
        if parsed is None or server is None:
            return rpc_error(message.id, -32602, f"unknown prompt: {presented}")
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
