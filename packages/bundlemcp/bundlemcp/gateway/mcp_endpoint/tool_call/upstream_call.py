"""Running one upstream tool call under timeout and cancellation."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from bundlemcp.gateway.composition import PresentedTool
from bundlemcp.gateway.mcp_endpoint.tool_call.call_outcome import (
    CANCELLED,
    UPSTREAM_FAILURE,
    CallOutcome,
)
from bundlemcp.gateway.mcp_endpoint.tool_call.call_status import CallStatus
from bundlemcp.gateway.mcp_endpoint.tool_call.client_relay import ClientRelay
from bundlemcp.gateway.runtime_config import CallTimeouts
from bundlemcp.gateway.streams import CallHandle
from bundlemcp.gateway.upstream import ClientFactory
from bundlemcp.store.sessions import SessionRecord, SessionStore, UpstreamBinding

log = structlog.get_logger(__name__)

ProgressCallback = Callable[[float, float | None, str | None], Awaitable[None]]

WATCHDOG_INTERVAL = 0.05


class UpstreamCall:
    """One attempt against the upstream, ending in an outcome rather than an exception.

    Three things can end it early: the caller cancels through the call handle,
    the upstream stays silent past the call timeout, or the total timeout runs
    out regardless of progress. Each is reported as a distinct outcome.
    """

    def __init__(
        self,
        *,
        client_factory: ClientFactory,
        sessions: SessionStore,
        tool: PresentedTool,
        arguments: dict[str, Any],
        headers: dict[str, str],
        session: SessionRecord,
        relay: ClientRelay,
        handle: CallHandle | None,
        timeouts: CallTimeouts,
        on_progress: ProgressCallback | None,
    ) -> None:
        # handle is None when the client sent no request id, so nothing can cancel it
        self._client_factory = client_factory
        self._sessions = sessions
        self._tool = tool
        self._arguments = arguments
        self._headers = headers
        self._session = session
        self._relay = relay
        self._handle = handle
        self._timeouts = timeouts
        self._on_progress = on_progress
        self._loop = asyncio.get_running_loop()
        self._started = self._loop.time()
        self._last_activity = self._started
        self._timeout_reason: str | None = None
        self._cancelled = False

    async def _progress(self, progress: float, total: float | None, message: str | None) -> None:
        self._last_activity = self._loop.time()  # PROT-2: reset the idle window
        if self._on_progress is not None:
            await self._on_progress(progress, total, message)

    async def _call(self) -> Any:
        handlers = self._relay.client_kwargs(self._session.client_capabilities)
        client = self._client_factory(self._tool.server, self._headers, **handlers)
        async with client:
            await self._sessions.set_binding(
                self._session.session_id,
                UpstreamBinding(
                    server_name=self._tool.server.name, identity_key=self._session.identity.sub
                ),
            )
            return await client.call_tool_mcp(
                self._tool.tool.name, self._arguments, progress_handler=self._progress
            )

    async def _watchdog(self, task: asyncio.Task[Any]) -> None:
        while not task.done():
            await asyncio.sleep(WATCHDOG_INTERVAL)
            now = self._loop.time()
            if now - self._started > self._timeouts.max_total:
                self._timeout_reason = "max_total_timeout"
                task.cancel()
                return
            idle_since = self._last_activity if self._timeouts.reset_on_progress else self._started
            if now - idle_since > self._timeouts.call:
                self._timeout_reason = "call_timeout"
                task.cancel()
                return

    async def _canceller(self, task: asyncio.Task[Any]) -> None:
        if self._handle is None:
            return
        await self._handle.cancel_event.wait()  # PROT-3 (may be set cross-replica)
        self._cancelled = True
        task.cancel()

    async def run(self) -> CallOutcome:
        task = asyncio.create_task(self._call())
        watchdog = asyncio.create_task(self._watchdog(task))
        canceller = asyncio.create_task(self._canceller(task))
        try:
            result = await task
            status = CallStatus.ERROR if result.is_error else CallStatus.SUCCESS  # MID-3
            return CallOutcome(status=status, result=result)
        except asyncio.CancelledError:
            if self._cancelled:
                return CallOutcome(
                    status=CallStatus.ERROR, error_message="cancelled", code=CANCELLED
                )
            if self._timeout_reason is not None:
                return CallOutcome(
                    status=CallStatus.ERROR,
                    error_message=self._timeout_reason,
                    code=UPSTREAM_FAILURE,
                )
            raise
        except Exception as exc:
            log.warning(
                "upstream.call_failed", server=self._tool.server.name, tool=self._tool.tool.name
            )
            return CallOutcome(
                status=CallStatus.ERROR, error_message=str(exc)[:500], code=UPSTREAM_FAILURE
            )
        finally:
            watchdog.cancel()
            canceller.cancel()
