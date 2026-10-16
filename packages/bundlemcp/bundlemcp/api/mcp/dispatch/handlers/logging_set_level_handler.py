import structlog
from fastapi import Response
from mcp.types import INVALID_PARAMS

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.domain.servers.server_capability import ServerCapability
from bundlemcp.domain.sessions.log_levels import LOG_LEVELS

log = structlog.get_logger(__name__)


class LoggingSetLevelHandler:
    """Remember the level on the session and pass it to the members that log.

    Each member that advertises logging is told the level on the upstream
    session bound to the client's session, so what it sends between calls is
    already filtered; the gateway filters again before relaying.
    """

    def __init__(self, sessions: SessionStore, fanout: MemberFanout) -> None:
        self._sessions = sessions
        self._fanout = fanout

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        level = message.param("level")
        if level not in LOG_LEVELS:
            return rpc_error(message.id, INVALID_PARAMS, f"unknown log level {level!r}")
        if ctx.session is not None:  # a handshake client's level lives on its session
            updated = await self._sessions.set_log_level(ctx.session.session_id, level)
            if updated is not None:
                ctx.session.log_level = level
            for server in self._fanout.members(ctx, ServerCapability.LOGGING):
                try:
                    await self._fanout.call(
                        ctx, server, lambda client: client.set_logging_level(level), bound=True
                    )
                except Exception:
                    log.warning("logging.set_level_failed", server=server.name, exc_info=True)
        return rpc_result(message.id, ctx.shape({}))
