from typing import Any

import structlog
from fastapi import Response
from mcp.types import PromptReference, ResourceTemplateReference

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout, dump
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.server_capability import ServerCapability

log = structlog.get_logger(__name__)

EMPTY_COMPLETION = {"completion": {"values": [], "hasMore": False}}
MAX_COMPLETIONS = 100  # the protocol's ceiling on values in one completion result


class CompletionHandler:
    """Answer completion/complete for a bundle prompt here; otherwise route it to the owning
    member: a prompt ref is de-prefixed, a resource-template ref is resolved by asking each
    member in turn."""

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
            if parsed is None:
                return self._bundle_prompt(ctx, message, presented, argument)
            server = ctx.view.servers.get(parsed.server)
            if server is None:
                return rpc_error(message.id, -32602, f"unknown prompt ref: {presented}")
            member_ref = PromptReference(type="ref/prompt", name=parsed.name)
            candidates = [server] if server.advertises(ServerCapability.COMPLETIONS) else []
        elif ref.get("type") == "ref/resource":
            member_ref = ResourceTemplateReference(type="ref/resource", uri=ref.get("uri", ""))
            # URI is not prefixed → fan-out over the members that complete at all
            candidates = self._fanout.members(ctx, ServerCapability.COMPLETIONS)
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

    @staticmethod
    def _bundle_prompt(
        ctx: RequestContext, message: JsonRpcMessage, name: str, argument: dict[str, Any]
    ) -> Response:
        """Complete from the argument's suggested values; no member is contacted."""
        # BPR-5
        prompt = ctx.view.prompt(name)
        if prompt is None:
            return rpc_error(message.id, -32602, f"unknown prompt ref: {name}")
        declared = prompt.argument(str(argument.get("name", "")))
        matches = declared.completions(str(argument.get("value", ""))) if declared else []
        completion = {
            "values": matches[:MAX_COMPLETIONS],
            "total": len(matches),
            "hasMore": len(matches) > MAX_COMPLETIONS,
        }
        return rpc_result(message.id, ctx.shape({"completion": completion}))
