"""One tools/call from admission to audit: authorise, meter, drive the upstream, account."""

import asyncio
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import Response

from bundlemcp.api.http.log_context import bind_request_fields
from bundlemcp.api.mcp.protocol.dialect import ProtocolEra
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.relay import (
    CallEvents,
    InputChannel,
    ParkingChannel,
    PreansweredChannel,
    RelayMode,
    RelayRejected,
    RequestState,
    ResumeInputs,
    arguments_digest,
    input_required_result,
)
from bundlemcp.api.mcp.relay.client_relay import ClientRelay, NotificationSink
from bundlemcp.api.mcp.tool_call.admitted_call import AdmittedCall
from bundlemcp.api.mcp.tool_call.call_outcome import (
    UPSTREAM_FAILURE,
    CallOutcome,
)
from bundlemcp.api.mcp.tool_call.call_response import (
    BufferedCallResponse,
    StreamedCallResponse,
)
from bundlemcp.api.mcp.tool_call.call_status import CallStatus
from bundlemcp.api.mcp.tool_call.request_audit import request_audit
from bundlemcp.api.mcp.tool_call.tool_call_support import ToolCallSupport
from bundlemcp.api.mcp.tool_call.upstream_call import ProgressCallback, UpstreamCall
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.observability.gateway_metrics import ToolCallStatus
from bundlemcp.application.metering.idempotency_key import new_idempotency_key
from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.serving.call_refusal import CallRefusal
from bundlemcp.application.serving.call_settlement import CallSettlement
from bundlemcp.application.serving.chain_call import ChainCall
from bundlemcp.application.serving.tool_chain import ToolChain
from bundlemcp.domain.access.credential_headers import CredentialHeaders
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.servers.upstream_reach import UpstreamReach
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_oauth_not_configured import UpstreamOAuthNotConfigured

log = structlog.get_logger(__name__)

NO_CIPHER = "input_required is unavailable on this gateway: no token encryption keys configured"


class ToolCall:
    """The state of one tools/call as it moves through the endpoint's chain.

    ``run`` admits the call, settles what the later steps need into an
    ``AdmittedCall`` and decides the response shape; the two response renderers
    call back into ``execute`` and ``finish`` (or ``conclude``, which does both
    and tells the client), handing each step that admitted call, so the
    buffered and streamed paths share every step except how bytes leave.
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
        # from the first leg, which marks this one as a later leg of that invocation
        self._support = support
        self._ctx = ctx
        self._message = message
        self._tool = tool
        bind_request_fields(server=tool.server.name, tool=tool.tool.name)
        self._resume = resume
        self._preanswered = preanswered
        self._correlation_id = uuid.uuid4().hex
        self._arguments: dict[str, Any] = message.param("arguments", {})
        endpoint = ctx.view.endpoint
        self._chain = ToolChain.for_endpoint(
            support.profiles.get(endpoint.profile), support.call_stages
        )
        self._call = ChainCall(
            context=MeterContext(
                sub=ctx.identity.sub,
                email=ctx.identity.user_email,
                oidc_issuer=ctx.identity.oidc_issuer,
                oidc_sub=ctx.identity.oidc_sub,
                auth_method=ctx.identity.auth_method,
                endpoint=endpoint.name,
                profile=endpoint.profile,
                bundle=ctx.view.bundle.name,
                session_id=ctx.session.session_id if ctx.session is not None else None,
                server=tool.server.name,
                tool=tool.tool.name,
                idempotency_key=idempotency_key or new_idempotency_key(),
                headers=CredentialHeaders.removed_from(ctx.request.headers),
            ),
            audit=request_audit(ctx, message.param("name", "")).resolved(tool),
            resumed=idempotency_key is not None,
        )

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

    def detach(self, work: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """Run ``work`` past the end of the response, keeping the task referenced."""
        task = asyncio.create_task(work)
        self._support.detached.add(task)
        task.add_done_callback(self._support.detached.discard)
        return task

    async def run(self) -> Response:
        received = time.monotonic()
        # the upstreams spec: resolve the upstream bearer BEFORE metering, so an unconnected
        # upstream is never debited.
        try:
            forwarded, credentials = await self._resolve_headers()
        except UpstreamOAuthNotConfigured:
            await self._chain.settle(
                self._call, CallSettlement.failed("upstream OAuth not configured")
            )
            return rpc_error(
                self.rpc_id, UPSTREAM_FAILURE, "upstream OAuth not configured on this gateway"
            )
        except NeedsConnect:
            await self._chain.settle(self._call, CallSettlement.failed("upstream_not_connected"))
            return rpc_error(
                self.rpc_id,
                UPSTREAM_FAILURE,
                self._support.credentials.connect_hint(self._tool.server),
            )

        refusal = await self._chain.admit(self._call)
        if refusal is not None:
            return await self._refuse(refusal, received)

        admitted = AdmittedCall(
            forwarded=forwarded,
            credentials=credentials,
            timeouts=await self._support.runtime_config.call_timeouts(),
            handle=self._support.registry.register_call(self._ctx.call_key, str(self.rpc_id))
            if self.rpc_id is not None
            else None,
        )
        # with a progressToken, stream progress as SSE and deliver the
        # result as the final event. A modern client is always streamed,
        # so closing the stream is its cancellation signal. Otherwise the
        # buffered JSON path, which only a handshake client reaches.
        if self._message.progress_token is not None or self._ctx.era is ProtocolEra.STATELESS:
            return await StreamedCallResponse(self._message.progress_token).render(self, admitted)
        return await BufferedCallResponse().render(self, admitted)

    async def _resolve_headers(self) -> tuple[dict[str, str], dict[str, str]]:
        # the upstreams spec: the upstream OAuth bearer wins over a forwarded header
        return await self._support.leases.headers(self._ctx, self._tool.server)

    async def _refuse(self, refusal: CallRefusal, received: float) -> Response:
        """End the call a stage refused, in words the person behind the client can read."""
        await self._chain.settle(self._call, CallSettlement.refused(refusal.reason))
        endpoint = self._ctx.view.endpoint.name
        # metering is the one call stage that refuses
        self._support.metrics.metering_denied(endpoint=endpoint)
        self._support.metrics.tool_call_finished(
            endpoint=endpoint,
            server=self._tool.server.name,
            status=ToolCallStatus.DENIED,
            seconds=time.monotonic() - received,
        )
        if refusal.user_message:
            # a tool error result, so the model relays the text verbatim
            content = [{"type": "text", "text": refusal.user_message}]
            return rpc_result(self.rpc_id, self.shape({"content": content, "isError": True}))
        return rpc_error(self.rpc_id, UPSTREAM_FAILURE, refusal.reason)

    async def execute(
        self,
        admitted: AdmittedCall,
        channel: InputChannel | None,
        on_progress: ProgressCallback | None,
        on_notification: NotificationSink | None,
    ) -> CallOutcome:
        """Drive the upstream inside one span, counted as in flight on its server until it ends.

        The span names the endpoint, server, tool and outcome. ``channel`` is
        how an upstream's request for input reaches the client; None sends it
        over a handshake client's GET stream.
        """
        metrics = self._support.metrics
        attributes = {
            "bundlemcp.endpoint": self._ctx.view.endpoint.name,
            "bundlemcp.server": self._tool.server.name,
            "bundlemcp.tool": self._tool.tool.name,
        }
        metrics.upstream_call_started(server=self._tool.server.name)
        reached = False
        try:
            with self._support.tracer.span("mcp.upstream_call", attributes) as span:
                outcome = await self._execute(admitted, channel, on_progress, on_notification)
                span.set_attribute("bundlemcp.status", outcome.status.value)
            reached = outcome.reached_upstream
        finally:
            metrics.upstream_call_finished(server=self._tool.server.name, ok=reached)
        return outcome

    async def _execute(
        self,
        admitted: AdmittedCall,
        channel: InputChannel | None,
        on_progress: ProgressCallback | None,
        on_notification: NotificationSink | None,
    ) -> CallOutcome:
        """Drive the upstream once; act on what an upstream refusal says.

        A 401 from an upstream-OAuth server forces a token refresh and one
        retry; a 403 insufficient_scope records the scopes the next
        connect must request and asks the caller to reconnect. The
        same chain call is reused, so an internal retry does not ask the
        metering hook again.
        """
        attempt = self._upstream_call(
            admitted, admitted.credentials, channel, on_progress, on_notification
        )
        outcome = await attempt.run()
        if outcome.reached_upstream:
            return outcome
        server = self._tool.server
        step_up = attempt.responses.insufficient_scope
        if step_up is not None and server.uses_upstream_oauth:
            return await self._step_up(outcome, step_up.challenge.scope or [])
        if not attempt.responses.saw_unauthorized:
            return outcome
        if not server.uses_upstream_oauth:
            return outcome.model_copy(
                update={"error_message": "the upstream server refused the gateway's credential"}
            )
        try:
            refreshed = await self._support.credentials.headers_for(
                server, self._ctx.identity, force_refresh=True
            )
        except (NeedsConnect, UpstreamOAuthNotConfigured):
            return outcome.model_copy(
                update={"error_message": self._support.credentials.connect_hint(server)}
            )
        return await self._upstream_call(
            admitted, refreshed, channel, on_progress, on_notification
        ).run()

    async def _step_up(self, outcome: CallOutcome, scopes: list[str]) -> CallOutcome:
        """Remember the demanded scopes and tell the caller to reconnect."""
        server = self._tool.server
        await self._support.credentials.request_step_up(server, scopes)
        needed = f" ({' '.join(scopes)})" if scopes else ""
        return outcome.model_copy(
            update={
                "error_message": f"the upstream needs additional permission{needed} — "
                f"reconnect at {self._support.credentials.connect_url(server)}"
            }
        )

    async def conclude(
        self,
        admitted: AdmittedCall,
        events: CallEvents,
        channel: InputChannel | None,
        on_progress: ProgressCallback | None,
        on_notification: NotificationSink | None,
        started: float,
    ) -> None:
        # the detached runner is what lets a parked call survive its response
        """Execute, account, and tell the streaming client how it ended.

        Runs detached from the response so that a call which asked the client
        for input keeps going after that response has been sent.
        """
        outcome = await self.execute(admitted, channel, on_progress, on_notification)
        if outcome.status is CallStatus.INPUT_REQUIRED:
            try:
                state = await self._pause(
                    admitted, "passthrough", upstream_state=outcome.input_required.request_state
                )
            except RelayRejected as exc:
                outcome = CallOutcome(
                    status=CallStatus.ERROR, error_message=str(exc), code=UPSTREAM_FAILURE
                )
            else:
                # the invocation continues on the client's retry
                self._release(admitted)
                await self._chain.settle(
                    self._call,
                    CallSettlement(
                        status=AuditStatus.INPUT_REQUIRED,
                        outcome=None,
                        duration_ms=int((time.monotonic() - started) * 1000),
                    ),
                )
                requests = outcome.input_required.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )["inputRequests"]
                await events.emit(
                    "input_required",
                    {"result": self.shape(input_required_result(requests, state))},
                )
                return
        await self.finish(admitted, outcome, started)
        await events.emit("result", outcome.body(self.shape))

    async def client_disconnected(self) -> bool:
        """Whether the client has gone away while this call's response is pending."""
        return await self._ctx.request.is_disconnected()

    def disconnected(self, admitted: AdmittedCall) -> None:
        # a disconnect is accounted for as a cancellation
        """The client went away mid-call: end the upstream call.

        The call is then accounted for as cancelled. After the upstream call
        has returned nothing waits on the cancellation, so a late disconnect
        changes nothing.
        """
        if admitted.handle is not None:
            admitted.handle.cancel_event.set()

    def input_channel(self, admitted: AdmittedCall, events: CallEvents) -> InputChannel | None:
        # which relay strategy serves a mid-request tool response
        """How an upstream's request for input reaches this streamed client.

        None for a handshake client, whose GET stream carries the request; a
        re-run answers from the retry it carries; otherwise the call parks
        until the client retries with its answers.
        """
        if self._ctx.era is ProtocolEra.SESSION:
            return None  # the GET stream relay
        if self._preanswered is not None:
            return PreansweredChannel(self._preanswered)

        async def seal_parked() -> str:
            return await self._pause(admitted, "parked")

        return ParkingChannel(
            self._support.registry,
            events,
            seal_parked,
            self.shape,
            admitted.timeouts.max_total,
        )

    async def _pause(
        self, admitted: AdmittedCall, mode: RelayMode, upstream_state: str | None = None
    ) -> str:
        """Seal the state the client's retry must echo, and tell the chain the leg waits."""
        cipher = self._support.state_cipher
        if cipher is None:
            raise RelayRejected(NO_CIPHER)
        expires_at = time.time() + admitted.timeouts.max_total
        state = RequestState(
            correlation_id=self._correlation_id,
            mode=mode,
            target=self._message.param("name", ""),
            arguments_digest=arguments_digest(self._arguments),
            sub=self._ctx.identity.sub,
            idempotency_key=self._call.context.idempotency_key,
            expires_at=expires_at,
            upstream_state=upstream_state,
        ).seal(cipher)
        await self._chain.pause(self._call, expires_at)
        return state

    def _upstream_call(
        self,
        admitted: AdmittedCall,
        credentials: dict[str, str],
        channel: InputChannel | None,
        on_progress: ProgressCallback | None,
        on_notification: NotificationSink | None,
    ) -> UpstreamCall:
        relay = ClientRelay(
            self._support.registry,
            self._support.signals,
            self._support.presence,
            self._ctx.routing_key,
            admitted.timeouts.max_total,
            log_level=self._ctx.log_level,
            on_notification=on_notification,
            channel=channel,
        )
        return UpstreamCall(
            leases=self._support.leases,
            ctx=self._ctx,
            tool=self._tool,
            arguments=self._arguments,
            forwarded=admitted.forwarded,
            credentials=credentials,
            relay=relay,
            handle=admitted.handle,
            timeouts=admitted.timeouts,
            on_progress=on_progress,
            raw_input_required=self._ctx.era is ProtocolEra.STATELESS,
            resume=self._resume,
        )

    async def _report_health(self, outcome: CallOutcome) -> None:
        """Tell the upstream's health whether this call reached it; never fails the call."""
        server = self._tool.server
        health = self._support.upstream_health
        try:
            match outcome.upstream_reach:
                case UpstreamReach.UNREACHABLE:
                    await health.failed(server.id, outcome.error_message or "unreachable")
                case UpstreamReach.ANSWERED:
                    await health.succeeded(server.id, server.health_status)
        except Exception:
            log.warning("health.report_failed", server=server.name, exc_info=True)

    def _release(self, admitted: AdmittedCall) -> None:
        """Stop addressing cancellations to this call; releasing twice is harmless."""
        if admitted.handle is not None:
            self._support.registry.unregister_call(admitted.handle)

    async def finish(self, admitted: AdmittedCall, outcome: CallOutcome, started: float) -> None:
        """Account for the call: release the handle and tell every stage how it ended."""
        self._release(admitted)
        self._support.metrics.tool_call_finished(
            endpoint=self._ctx.view.endpoint.name,
            server=self._tool.server.name,
            status=ToolCallStatus.SUCCESS
            if outcome.status is CallStatus.SUCCESS
            else ToolCallStatus.ERROR,
            seconds=time.monotonic() - started,
        )
        await self._report_health(outcome)
        status = AuditStatus.SUCCESS if outcome.status is CallStatus.SUCCESS else AuditStatus.ERROR
        await self._chain.settle(
            self._call,
            CallSettlement(
                status=status,
                outcome=outcome.meter_outcome,
                duration_ms=int((time.monotonic() - started) * 1000),
                error_message=outcome.error_message,
            ),
        )
