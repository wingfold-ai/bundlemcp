from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.upstream.member_notification import MemberLogMessage
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.log_levels import at_least


class MemberLogMessageHandler:
    """Delivers a member's log message to the client its upstream session is dedicated to.

    Only at or above the level that client asked for; a message heard on a
    session shared between requests belongs to no client and is dropped.
    """

    def __init__(self, sessions: SessionStore, signals: SignalBus) -> None:
        self._sessions = sessions
        self._signals = signals

    async def handle(
        self, server: McpServer, notification: MemberLogMessage, *, bound_to: str | None
    ) -> None:
        if bound_to is None:
            return
        record = await self._sessions.load(bound_to)
        if record is None or record.log_level is None:
            return
        if at_least(notification.level, record.log_level):
            await self._signals.deliver(bound_to, notification.notification())
