from fastapi import Response
from mcp.types import INVALID_PARAMS

from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.log_levels import LOG_LEVELS
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.contracts.live_state.session_store import SessionStore


class LoggingSetLevelHandler:
    """Remember the level on the session; each upstream call relays messages from it on."""

    def __init__(self, sessions: SessionStore) -> None:
        self._sessions = sessions

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        level = message.param("level")
        if level not in LOG_LEVELS:
            return rpc_error(message.id, INVALID_PARAMS, f"unknown log level {level!r}")
        if ctx.session is not None:  # PROT-7: a handshake client's level lives on its session
            await self._sessions.set_log_level(ctx.session.session_id, level)
        return rpc_result(message.id, ctx.shape({}))
