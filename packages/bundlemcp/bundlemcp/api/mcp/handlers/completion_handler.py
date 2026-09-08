import structlog
from fastapi import Response
from mcp.types import PromptReference, ResourceTemplateReference

from bundlemcp.api.mcp.handlers.member_fanout import MemberFanout, dump
from bundlemcp.api.mcp.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.request_context import RequestContext
from bundlemcp.domain.bundles.presented_name import PresentedName

log = structlog.get_logger(__name__)

EMPTY_COMPLETION = {"completion": {"values": [], "hasMore": False}}


class CompletionHandler:
    """Route completion/complete to the owning member: a prompt ref is de-prefixed,
    a resource-template ref is resolved by asking each member in turn."""

    def __init__(self, fanout: MemberFanout) -> None:
        self._fanout = fanout

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # PROT-9
        ref = message.param("ref", {})
        argument = message.param("argument", {})
        context = message.param("context", {}).get("arguments")

        if ref.get("type") == "ref/prompt":
            presented = ref.get("name", "")
            parsed = PresentedName.parse(presented)
            server = ctx.view.servers.get(parsed.server) if parsed else None
            if parsed is None or server is None:
                return rpc_error(message.id, -32602, f"unknown prompt ref: {presented}")
            member_ref = PromptReference(type="ref/prompt", name=parsed.name)
            candidates = [server]
        elif ref.get("type") == "ref/resource":
            member_ref = ResourceTemplateReference(type="ref/resource", uri=ref.get("uri", ""))
            candidates = list(ctx.view.servers.values())  # URI is not prefixed → fan-out
        else:
            return rpc_error(message.id, -32602, f"unsupported completion ref: {ref.get('type')}")

        for server in candidates:
            try:
                result = await self._fanout.call(
                    ctx, server, lambda client: client.complete_mcp(member_ref, argument, context)
                )
            except Exception:
                log.warning("completion.member_failed", server=server.name)
                continue
            return rpc_result(message.id, ctx.shape(dump(result)))
        return rpc_result(message.id, ctx.shape(dict(EMPTY_COMPLETION)))
