"""One tools/call from admission to audit: authorise, meter, drive the upstream, account."""

import asyncio
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import Response

from bundlemcp.gateway.composition import PresentedTool
from bundlemcp.gateway.dialect import Era
from bundlemcp.gateway.mcp_endpoint.forwarded_headers import forwarded_headers
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.mrtr import (
    CallEvents,
    InputChannel,
    ParkingChannel,
    PreansweredChannel,
    RelayRejected,
    RequestState,
    ResumeInputs,
    arguments_digest,
    input_required_result,
)
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext
from bundlemcp.gateway.mcp_endpoint.tool_call.audit_context import AuditContext
from bundlemcp.gateway.mcp_endpoint.tool_call.call_outcome import (
    UPSTREAM_FAILURE,
    CallOutcome,
)
from bundlemcp.gateway.mcp_endpoint.tool_call.call_response import (
    BufferedCallResponse,
    StreamedCallResponse,
)
from bundlemcp.gateway.mcp_endpoint.tool_call.call_status import CallStatus
from bundlemcp.gateway.mcp_endpoint.tool_call.client_relay import ClientRelay, NotificationSink
from bundlemcp.gateway.mcp_endpoint.tool_call.tool_call_support import ToolCallSupport
from bundlemcp.gateway.mcp_endpoint.tool_call.upstream_call import ProgressCallback, UpstreamCall
from bundlemcp.gateway.metering import MeterContext, MeterDecision, new_idempotency_key
from bundlemcp.gateway.runtime_config import CallTimeouts
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import CallHandle
from bundlemcp.models import AuditStatus
from bundlemcp.oauth.upstream_client import NeedsConnect, UpstreamOAuthNotConfigured

log = structlog.get_logger(__name__)

NO_CIPHER = "input_required is unavailable on this gateway: no token encryption keys configured"


class ToolCall:
    """The state of one tools/call as it moves through the pipeline.

    ``run`` decides the response shape and drives the steps in order; the two
    response renderers call back into ``execute`` and ``finish`` (or
    ``conclude``, which does both and tells the client) so the buffered and
    streamed paths share every step except how bytes leave.
    """

    def __init__(
        self,
        support: ToolCallSupport,
        ctx: RequestContext,
        message: JsonRpcMessage,
        tool: PresentedTool,
        *,
        resume: ResumeInputs | None = None,
        preanswered: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        # resume: a retry's answers for an upstream that asked for input itself
        # (passthrough); preanswered: answers for an upstream that will ask again
        # because its parked call was lost (re-run); idempotency_key: carried over
        # from the first leg so the retry is charged once (MID-3)
        self._support = support
        self._ctx = ctx
        self._message = message
        self._tool = tool
        self._resume = resume
        self._preanswered = preanswered
        self._idempotency_key = idempotency_key or new_idempotency_key()
        self._correlation_id = uuid.uuid4().hex
        self._arguments: dict[str, Any] = message.param("arguments", {})
        self._audit = AuditContext.for_request(ctx, message.param("name", "")).resolved(tool)
        self._headers: dict[str, str] = {}
        self._meter: MeterContext | None = None
        self._timeouts: CallTimeouts | None = None
        self._handle: CallHandle | None = None
        self._events: CallEvents | None = None

    @property
    def rpc_id(self) -> Any:
        return self._message.id

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    @property
    def signals(self) -> SignalBus:
        return self._support.signals

    @property
    def shape(self) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """How a result payload is decorated for this client's revision."""
        return self._ctx.shape

    def attach(self, events: CallEvents) -> None:
        """Where this call's events go once it is streamed."""
        self._events = events

    def detach(self, work: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """Run ``work`` past the end of the response, keeping the task referenced."""
        task = asyncio.create_task(work)
        self._support.detached.add(task)
        task.add_done_callback(self._support.detached.discard)
        return task

    async def run(self) -> Response:
        # spec 23: resolve the upstream bearer BEFORE metering, so an unconnected
        # upstream is never debited.
        try:
            self._headers = await self._resolve_headers()
        except UpstreamOAuthNotConfigured:
            self._record(AuditStatus.ERROR, error_message="upstream OAuth not configured")
            return rpc_error(
                self.rpc_id, UPSTREAM_FAILURE, "upstream OAuth not configured on this gateway"
            )
        except NeedsConnect:
            self._record(AuditStatus.ERROR, error_message="upstream_not_connected")
            return rpc_error(
                self.rpc_id,
                UPSTREAM_FAILURE,
                self._support.credentials.connect_hint(self._tool.server),
            )

        decision = await self._meter_pre_call()
        if not decision.allowed:
            self._record(AuditStatus.DENIED, denied_reason=decision.reason or "denied")
            return rpc_error(self.rpc_id, UPSTREAM_FAILURE, decision.reason or "call denied")

        self._timeouts = await self._support.runtime_config.call_timeouts()
        if self.rpc_id is not None:
            self._handle = self._support.registry.register_call(
                self._ctx.routing_key, str(self.rpc_id)
            )
        # PROT-1: with a progressToken, stream progress as SSE and deliver the
        # result as the final event. PROT-19: a modern client is always streamed,
        # so closing the stream is its cancellation signal. Otherwise the
        # buffered JSON path.
        if self._message.progress_token is not None or self._ctx.era is Era.MODERN:
            return await StreamedCallResponse(self._message.progress_token).render(self)
        return await BufferedCallResponse().render(self)

    async def _resolve_headers(self) -> dict[str, str]:
        headers = forwarded_headers(
            self._ctx.request.headers, self._tool.server, self._ctx.identity.sub
        )
        upstream = await self._support.credentials.headers_for(
            self._tool.server, self._ctx.identity
        )
        headers.update(upstream)  # spec 23: the upstream OAuth bearer wins
        return headers

    async def _meter_pre_call(self) -> MeterDecision:
        self._meter = MeterContext(
            sub=self._ctx.identity.sub,
            email=self._ctx.identity.user_email,
            endpoint=self._ctx.view.endpoint.name,
            bundle=self._ctx.view.bundle.name,
            server=self._tool.server.name,
            tool=self._tool.tool.name,
            idempotency_key=self._idempotency_key,  # MID-3: once per client invocation
        )
        try:
            return await self._support.metering.pre_call(self._meter)
        except Exception:
            log.error("metering.pre_call_failed", exc_info=True)
            # MID-3: fail-open is the gateway's policy, not the hook's property.
            return MeterDecision(
                allowed=self._support.metering_fail_open, reason="metering_unavailable"
            )

    async def execute(
        self, on_progress: ProgressCallback | None, on_notification: NotificationSink | None
    ) -> CallOutcome:
        """Drive the upstream once; on an upstream-OAuth failure, refresh and retry once."""
        outcome = await self._upstream_call(self._headers, on_progress, on_notification).run()
        # UPO-4 reactive: a failure despite a fresh token forces a refresh and one
        # retry. The same metering context is reused — an internal retry does
        # NOT re-fire pre_call (MID-3).
        if not outcome.reached_upstream and self._tool.server.uses_upstream_oauth:
            try:
                refreshed = await self._support.credentials.headers_for(
                    self._tool.server, self._ctx.identity, force_refresh=True
                )
            except (NeedsConnect, UpstreamOAuthNotConfigured):
                return outcome  # keep the original error outcome
            outcome = await self._upstream_call(
                {**self._headers, **refreshed}, on_progress, on_notification
            ).run()
        return outcome

    async def conclude(
        self,
        on_progress: ProgressCallback | None,
        on_notification: NotificationSink | None,
        started: float,
    ) -> None:
        """Execute, account, and tell the streaming client how it ended.

        Runs detached from the response so that a call which asked the client
        for input keeps going after that response has been sent (PROT-18).
        """
        assert self._events is not None  # attached by the streamed renderer
        outcome = await self.execute(on_progress, on_notification)
        if outcome.status is CallStatus.INPUT_REQUIRED:
            try:
                state = self._seal_state(
                    mode="passthrough", upstream_state=outcome.input_required.request_state
                )
            except RelayRejected as exc:
                outcome = CallOutcome(
                    status=CallStatus.ERROR, error_message=str(exc), code=UPSTREAM_FAILURE
                )
            else:
                # The invocation continues on the client's retry: no post_call yet.
                self._release()
                self._record(
                    AuditStatus.INPUT_REQUIRED,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
                requests = outcome.input_required.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )["inputRequests"]
                await self._events.emit(
                    "input_required",
                    {"result": self.shape(input_required_result(requests, state))},
                )
                return
        await self.finish(outcome, started)
        await self._events.emit("result", outcome.body(self.shape))

    def disconnected(self) -> None:
        """The client closed the response stream mid-call: end the upstream call.

        The detached runner then accounts for the call as cancelled (PROT-19).
        """
        if self._handle is not None:
            self._handle.cancel_event.set()

    def _channel(self) -> InputChannel | None:
        """How an upstream's request for input reaches this client (PROT-18)."""
        if self._ctx.era is Era.HANDSHAKE:
            return None  # PROT-4: the GET stream relay
        if self._preanswered is not None:
            return PreansweredChannel(self._preanswered)
        assert self._events is not None and self._timeouts is not None
        return ParkingChannel(
            self._support.registry,
            self._events,
            self._seal_state,
            self.shape,
            self._timeouts.max_total,
        )

    def _seal_state(self, mode: str = "parked", upstream_state: str | None = None) -> str:
        cipher = self._support.state_cipher
        if cipher is None:
            raise RelayRejected(NO_CIPHER)
        assert self._timeouts is not None
        return RequestState(
            correlation_id=self._correlation_id,
            mode=mode,  # type: ignore[arg-type]
            presented_tool=self._message.param("name", ""),
            arguments_digest=arguments_digest(self._arguments),
            sub=self._ctx.identity.sub,
            idempotency_key=self._idempotency_key,
            expires_at=time.time() + self._timeouts.max_total,
            upstream_state=upstream_state,
        ).seal(cipher)

    def _upstream_call(
        self,
        headers: dict[str, str],
        on_progress: ProgressCallback | None,
        on_notification: NotificationSink | None,
    ) -> UpstreamCall:
        assert self._timeouts is not None  # set by run() before execute() is reachable
        relay = ClientRelay(
            self._support.registry,
            self._support.signals,
            self._ctx.routing_key,
            self._timeouts.max_total,
            log_level=self._ctx.log_level,
            on_notification=on_notification,
            channel=self._channel(),
        )
        return UpstreamCall(
            client_factory=self._support.client_factory,
            sessions=self._support.sessions,
            tool=self._tool,
            arguments=self._arguments,
            headers=headers,
            session=self._ctx.session,
            # PROT-5: only capabilities the client advertised are offered upstream
            client_capabilities=self._ctx.client_capabilities,
            log_level=self._ctx.log_level,
            relay=relay,
            handle=self._handle,
            timeouts=self._timeouts,
            on_progress=on_progress,
            raw_input_required=self._ctx.era is Era.MODERN,
            resume=self._resume,
        )

    def _release(self) -> None:
        if self._handle is not None:
            self._support.registry.unregister_call(self._handle)
            self._handle = None

    async def finish(self, outcome: CallOutcome, started: float) -> None:
        """Account for the call: release the handle, tell metering, write the audit record."""
        self._release()
        duration_ms = int((time.monotonic() - started) * 1000)
        if self._meter is not None:
            try:
                await self._support.metering.post_call(
                    self._meter, outcome.status.value, duration_ms
                )  # refund trigger
            except Exception:
                log.error("metering.post_call_failed", exc_info=True)
        status = AuditStatus.SUCCESS if outcome.status is CallStatus.SUCCESS else AuditStatus.ERROR
        self._record(status, error_message=outcome.error_message, duration_ms=duration_ms)

    def _record(self, status: AuditStatus, **details: Any) -> None:
        self._support.audit.record(self._audit.record(status, **details))
