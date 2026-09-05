"""One tools/call from admission to audit: authorise, meter, drive the upstream, account."""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import structlog
from fastapi import Response

from bundlemcp.gateway.composition import PresentedTool
from bundlemcp.gateway.dialect import Era
from bundlemcp.gateway.mcp_endpoint.forwarded_headers import forwarded_headers
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext
from bundlemcp.gateway.mcp_endpoint.tool_call.audit_context import AuditContext
from bundlemcp.gateway.mcp_endpoint.tool_call.call_outcome import (
    CANCELLED,
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
from bundlemcp.gateway.streams import CallHandle
from bundlemcp.models import AuditStatus
from bundlemcp.oauth.upstream_client import NeedsConnect, UpstreamOAuthNotConfigured

log = structlog.get_logger(__name__)


class ToolCall:
    """The state of one tools/call as it moves through the pipeline.

    ``run`` decides the response shape and drives the steps in order; the two
    response renderers call back into ``execute`` and ``finish`` so the buffered
    and streamed paths share every step except how bytes leave.
    """

    def __init__(
        self,
        support: ToolCallSupport,
        ctx: RequestContext,
        message: JsonRpcMessage,
        tool: PresentedTool,
    ) -> None:
        self._support = support
        self._ctx = ctx
        self._message = message
        self._tool = tool
        self._arguments: dict[str, Any] = message.param("arguments", {})
        self._audit = AuditContext.for_request(ctx, message.param("name", "")).resolved(tool)
        self._headers: dict[str, str] = {}
        self._meter: MeterContext | None = None
        self._timeouts: CallTimeouts | None = None
        self._handle: CallHandle | None = None

    @property
    def rpc_id(self) -> Any:
        return self._message.id

    @property
    def shape(self) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """How a result payload is decorated for this client's revision."""
        return self._ctx.shape

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
            idempotency_key=new_idempotency_key(),  # MID-3: once per client invocation
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
        )
        # PROT-5: only capabilities the client advertised are offered upstream.
        # A modern client has no stream to relay on; its requests for input are
        # answered with input_required (PROT-18), so no relay handler is offered
        # and an upstream that needs one fails fast instead of waiting.
        capabilities = self._ctx.client_capabilities if self._ctx.era is Era.HANDSHAKE else {}
        return UpstreamCall(
            client_factory=self._support.client_factory,
            sessions=self._support.sessions,
            tool=self._tool,
            arguments=self._arguments,
            headers=headers,
            session=self._ctx.session,
            client_capabilities=capabilities,
            log_level=self._ctx.log_level,
            relay=relay,
            handle=self._handle,
            timeouts=self._timeouts,
            on_progress=on_progress,
        )

    def disconnected(self, running: "asyncio.Task[CallOutcome]", started: float) -> None:
        """The client closed the response stream mid-call: cancel upstream, then account.

        Accounting cannot run inside the stream's teardown, so it continues on a
        detached task the support object keeps a reference to.
        """
        if self._handle is not None:
            self._handle.cancel_event.set()  # the canceller ends the upstream call
        else:
            running.cancel()
        task = asyncio.create_task(self._finish_after_disconnect(running, started))
        self._support.detached.add(task)
        task.add_done_callback(self._support.detached.discard)

    async def _finish_after_disconnect(
        self, running: "asyncio.Task[CallOutcome]", started: float
    ) -> None:
        try:
            outcome = await running
        except asyncio.CancelledError:
            outcome = CallOutcome(
                status=CallStatus.ERROR, error_message="cancelled", code=CANCELLED
            )
        await self.finish(outcome, started)

    async def finish(self, outcome: CallOutcome, started: float) -> None:
        """Account for the call: release the handle, tell metering, write the audit record."""
        if self._handle is not None:
            self._support.registry.unregister_call(self._handle)
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
