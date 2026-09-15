"""Running one upstream tool call under timeout and cancellation."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from mcp.types import LOG_LEVEL_META_KEY, InputRequiredResult, InputResponses
from pydantic import TypeAdapter

from bundlemcp.api.mcp.relay import ResumeInputs
from bundlemcp.api.mcp.relay.client_relay import ClientRelay
from bundlemcp.api.mcp.tool_call.call_outcome import (
    CANCELLED,
    UPSTREAM_FAILURE,
    CallOutcome,
)
from bundlemcp.api.mcp.tool_call.call_status import CallStatus
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.serving.call_handle import CallHandle
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.config.call_timeouts import CallTimeouts
from bundlemcp.domain.sessions.session_record import SessionRecord
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding

log = structlog.get_logger(__name__)

ProgressCallback = Callable[[float, float | None, str | None], Awaitable[None]]

WATCHDOG_INTERVAL = 0.05

input_responses_adapter: TypeAdapter[InputResponses] = TypeAdapter(InputResponses)


class UpstreamCall:
    """One attempt against the upstream, ending in an outcome rather than an exception.

    Three things can end it early: the caller cancels through the call handle,
    the upstream stays silent past the call timeout, or the total timeout runs
    out regardless of progress. Each is reported as a distinct outcome. A modern
    upstream may also answer that it needs client input, which is an outcome of
    its own rather than a failure.
    """

    def __init__(
        self,
        *,
        client_factory: UpstreamClientFactory,
        sessions: SessionStore,
        tool: PresentedTool,
        arguments: dict[str, Any],
        headers: dict[str, str],
        session: SessionRecord | None,
        client_capabilities: dict[str, Any],
        log_level: str | None,
        relay: ClientRelay,
        handle: CallHandle | None,
        timeouts: CallTimeouts,
        on_progress: ProgressCallback | None,
        raw_input_required: bool,
        resume: ResumeInputs | None,
    ) -> None:
        # handle is None when the client sent no request id, so nothing can cancel it;
        # session is None for a modern-era client, which has none to bind to (SES-15);
        # raw_input_required asks for the upstream's own input_required result instead
        # of letting the client library resolve it through the relay (PROT-18
        # passthrough); resume carries a retry's answers for the upstream
        self._client_factory = client_factory
        self._sessions = sessions
        self._tool = tool
        self._arguments = arguments
        self._headers = headers
        self._session = session
        self._client_capabilities = client_capabilities
        self._log_level = log_level
        self._relay = relay
        self._handle = handle
        self._timeouts = timeouts
        self._on_progress = on_progress
        self._raw_input_required = raw_input_required
        self._resume = resume
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
        handlers = self._relay.client_kwargs(self._client_capabilities)
        client = self._client_factory(self._tool.server, self._headers, **handlers)
        async with client:
            if self._session is not None:  # SES-6 bookkeeping, handshake sessions only
                await self._sessions.set_binding(
                    self._session.session_id,
                    UpstreamBinding(
                        server_name=self._tool.server.name,
                        identity_key=self._session.identity.sub,
                    ),
                )
            # PROT-20: a modern upstream emits log messages only when asked per request.
            meta = {LOG_LEVEL_META_KEY: self._log_level} if self._log_level is not None else None
            if not self._raw_input_required:
                return await client.call_tool_mcp(
                    self._tool.tool.name,
                    self._arguments,
                    progress_handler=self._progress,
                    meta=meta,
                )
            responses = (
                input_responses_adapter.validate_python(self._resume.responses)
                if self._resume is not None
                else None
            )
            return await client.session.call_tool(
                self._tool.tool.name,
                self._arguments,
                progress_callback=self._progress,
                input_responses=responses,
                request_state=self._resume.upstream_state if self._resume is not None else None,
                meta=meta,
                allow_input_required=True,
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
            if isinstance(result, InputRequiredResult):
                return CallOutcome(status=CallStatus.INPUT_REQUIRED, input_required=result)
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
