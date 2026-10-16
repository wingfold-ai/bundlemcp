"""Running one upstream tool call under timeout and cancellation."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from mcp.types import LOG_LEVEL_META_KEY, InputRequiredResult, InputResponses
from pydantic import TypeAdapter

from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.relay import ResumeInputs
from bundlemcp.api.mcp.relay.client_relay import ClientRelay
from bundlemcp.api.mcp.tool_call.call_outcome import (
    CANCELLED,
    UPSTREAM_FAILURE,
    CallOutcome,
)
from bundlemcp.api.mcp.tool_call.call_status import CallStatus
from bundlemcp.api.mcp.upstream.jsonrpc_code import jsonrpc_code
from bundlemcp.api.mcp.upstream.upstream_leases import UpstreamLeases
from bundlemcp.application.serving.call_handle import CallHandle
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.config.call_timeouts import CallTimeouts
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.servers.upstream_reach import UpstreamReach
from bundlemcp.domain.sessions.upstream_failure import UpstreamFailure
from bundlemcp.domain.sessions.upstream_retry_policy import UpstreamRetryPolicy

log = structlog.get_logger(__name__)

ProgressCallback = Callable[[float, float | None, str | None], Awaitable[None]]

WATCHDOG_INTERVAL = 0.05

input_responses_adapter: TypeAdapter[InputResponses] = TypeAdapter(InputResponses)

# a tool call may have side effects, so it is resent only when it cannot have run
TOOL_CALL_RETRY = UpstreamRetryPolicy(read_only=False)


class UpstreamCall:
    """One attempt against the upstream, ending in an outcome rather than an exception.

    Three things can end it early: the caller cancels through the call handle,
    the upstream stays silent past the call timeout, or the total timeout runs
    out regardless of progress. Each is reported as a distinct outcome. A modern
    upstream may also answer that it needs client input, which is an outcome of
    its own rather than a failure.

    A handshake client's call runs on the upstream session bound to its
    session. When that session expired upstream, or the request never left
    the gateway, the call is sent once more on a new session, so the client
    sees no error for an upstream that restarted.
    """

    def __init__(
        self,
        *,
        leases: UpstreamLeases,
        ctx: RequestContext,
        tool: PresentedTool,
        arguments: dict[str, Any],
        forwarded: dict[str, str],
        credentials: dict[str, str],
        relay: ClientRelay,
        handle: CallHandle | None,
        timeouts: CallTimeouts,
        on_progress: ProgressCallback | None,
        raw_input_required: bool,
        resume: ResumeInputs | None,
    ) -> None:
        # handle is None when the client sent no request id, so nothing can cancel it;
        # raw_input_required asks for the upstream's own input_required result instead
        # of letting the client library resolve it through the relay (
        # passthrough); resume carries a retry's answers for the upstream
        self._leases = leases
        self._ctx = ctx
        self._tool = tool
        self._arguments = arguments
        self._forwarded = forwarded
        self._credentials = credentials
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
        self.responses = ResponseLog()  # what the upstream answered below MCP

    async def _progress(self, progress: float, total: float | None, message: str | None) -> None:
        self._last_activity = self._loop.time()  # reset the idle window
        if self._on_progress is not None:
            await self._on_progress(progress, total, message)

    async def _call(self) -> Any:
        fresh = False
        while True:
            try:
                return await self._attempt(fresh=fresh)
            except Exception as exc:
                failure = UpstreamFailure.of(self.responses, jsonrpc_code=jsonrpc_code(exc))
                if not TOOL_CALL_RETRY.allows_retry(failure, retried=fresh):
                    raise
                log.info("upstream.call_retried", server=self._tool.server.name, failure=failure)
                fresh = True
                self.responses = ResponseLog()

    async def _attempt(self, *, fresh: bool) -> Any:
        # only capabilities the client advertised are offered upstream
        handlers = self._relay.client_kwargs(self._ctx.client_capabilities)
        request = self._leases.request(
            self._ctx,
            self._tool.server,
            forwarded=self._forwarded,
            credentials=self._credentials,
            handlers=handlers,
            bound=True,  # a handshake session's calls run on its own upstream session
            responses=self.responses,
            fresh=fresh,
        )
        async with self._leases.lease(request, self._ctx.session) as lease:
            client = lease.client
            # a modern upstream emits log messages only when asked per request.
            level = self._ctx.log_level
            meta = {LOG_LEVEL_META_KEY: level} if level is not None else None
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
            if self.responses.oversized_limit is not None:
                # the connection abandoned a message; the client may still be waiting on it
                self._timeout_reason = self._oversized_reason()
                task.cancel()
                return
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

    def _oversized_reason(self) -> str:
        return (
            f"upstream response too large: a message exceeded the "
            f"{self.responses.oversized_limit}-byte limit"
        )

    async def _canceller(self, task: asyncio.Task[Any]) -> None:
        if self._handle is None:
            return
        await self._handle.cancel_event.wait()  # may be set from another replica
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
            status = CallStatus.ERROR if result.is_error else CallStatus.SUCCESS
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
            message = (
                self._oversized_reason()
                if self.responses.oversized_limit is not None
                else str(exc)[:500]
            )
            return CallOutcome(
                status=CallStatus.ERROR,
                error_message=message,
                code=UPSTREAM_FAILURE,
                failure_reach=UpstreamReach.of_failure(
                    self.responses, jsonrpc_code=jsonrpc_code(exc)
                ),
            )
        finally:
            watchdog.cancel()
            canceller.cancel()
