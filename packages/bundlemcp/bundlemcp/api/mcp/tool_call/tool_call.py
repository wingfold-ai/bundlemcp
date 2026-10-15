"""One tools/call from admission to audit: authorise, meter, drive the upstream, account."""

import asyncio
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import Response

from bundlemcp.api.mcp.protocol.dialect import ProtocolEra
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.relay import (
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
from bundlemcp.api.mcp.relay.client_relay import ClientRelay, NotificationSink
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
from bundlemcp.application.metering.idempotency_key import new_idempotency_key
from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.serving.call_handle import CallHandle
from bundlemcp.application.serving.call_refusal import CallRefusal
from bundlemcp.application.serving.call_settlement import CallSettlement
from bundlemcp.application.serving.chain_call import ChainCall
from bundlemcp.application.serving.tool_chain import ToolChain
from bundlemcp.domain.access.credential_headers import CredentialHeaders
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.config.call_timeouts import CallTimeouts
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_oauth_not_configured import UpstreamOAuthNotConfigured

log = structlog.get_logger(__name__)

NO_CIPHER = "input_required is unavailable on this gateway: no token encryption keys configured"


class ToolCall:
    """The state of one tools/call as it moves through the endpoint's chain.

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
        # from the first leg, which marks this one as a later leg of that invocation
        self._support = support
        self._ctx = ctx
        self._message = message
        self._tool = tool
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
        self._headers: dict[str, str] = {}
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
        # the upstreams spec: resolve the upstream bearer BEFORE metering, so an unconnected
        # upstream is never debited.
        try:
            self._headers = await self._resolve_headers()
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
            return await self._refuse(refusal)

        self._timeouts = await self._support.runtime_config.call_timeouts()
        if self.rpc_id is not None:
            self._handle = self._support.registry.register_call(
                self._ctx.call_key, str(self.rpc_id)
            )
        # with a progressToken, stream progress as SSE and deliver the
        # result as the final event. A modern client is always streamed,
        # so closing the stream is its cancellation signal. Otherwise the
        # buffered JSON path.
        if self._message.progress_token is not None or self._ctx.era is ProtocolEra.STATELESS:
            return await StreamedCallResponse(self._message.progress_token).render(self)
        return await BufferedCallResponse().render(self)

    async def _resolve_headers(self) -> dict[str, str]:
        headers = self._support.header_forwarding.headers_for(
            self._ctx.request.headers, self._tool.server, self._ctx.identity
        )
        upstream = await self._support.credentials.headers_for(
            self._tool.server, self._ctx.identity, endpoint=self._ctx.view.endpoint.name
        )
        headers.update(upstream)  # the upstreams spec: the upstream OAuth bearer wins
        return headers

    async def _refuse(self, refusal: CallRefusal) -> Response:
        """End the call a stage refused, in words the person behind the client can read."""
        await self._chain.settle(self._call, CallSettlement.refused(refusal.reason))
        if refusal.user_message:
            # a tool error result, so the model relays the text verbatim
            content = [{"type": "text", "text": refusal.user_message}]
            return rpc_result(self.rpc_id, self.shape({"content": content, "isError": True}))
        return rpc_error(self.rpc_id, UPSTREAM_FAILURE, refusal.reason)

    async def execute(
        self, on_progress: ProgressCallback | None, on_notification: NotificationSink | None
    ) -> CallOutcome:
        """Drive the upstream once; act on what an upstream refusal says.

        A 401 from an upstream-OAuth server forces a token refresh and one
        retry; a 403 insufficient_scope records the scopes the next
        connect must request and asks the caller to reconnect. The
        same chain call is reused, so an internal retry does not ask the
        metering hook again.
        """
        attempt = self._upstream_call(self._headers, on_progress, on_notification)
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
            {**self._headers, **refreshed}, on_progress, on_notification
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
        on_progress: ProgressCallback | None,
        on_notification: NotificationSink | None,
        started: float,
    ) -> None:
        # the detached runner is what lets a parked call survive its response
        """Execute, account, and tell the streaming client how it ended.

        Runs detached from the response so that a call which asked the client
        for input keeps going after that response has been sent.
        """
        assert self._events is not None  # attached by the streamed renderer
        outcome = await self.execute(on_progress, on_notification)
        if outcome.status is CallStatus.INPUT_REQUIRED:
            try:
                state = await self._pause(
                    mode="passthrough", upstream_state=outcome.input_required.request_state
                )
            except RelayRejected as exc:
                outcome = CallOutcome(
                    status=CallStatus.ERROR, error_message=str(exc), code=UPSTREAM_FAILURE
                )
            else:
                # the invocation continues on the client's retry
                self._release()
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
                await self._events.emit(
                    "input_required",
                    {"result": self.shape(input_required_result(requests, state))},
                )
                return
        await self.finish(outcome, started)
        await self._events.emit("result", outcome.body(self.shape))

    async def client_disconnected(self) -> bool:
        """Whether the client has gone away while this call's response is pending."""
        return await self._ctx.request.is_disconnected()

    def disconnected(self) -> None:
        # a disconnect is accounted for as a cancellation
        """The client went away mid-call: end the upstream call.

        The call is then accounted for as cancelled.
        """
        if self._handle is not None:
            self._handle.cancel_event.set()

    def _channel(self) -> InputChannel | None:
        # which relay strategy serves a mid-request tool response
        """How an upstream's request for input reaches this client."""
        if self._ctx.era is ProtocolEra.SESSION:
            return None  # the GET stream relay
        if self._preanswered is not None:
            return PreansweredChannel(self._preanswered)
        assert self._events is not None and self._timeouts is not None
        return ParkingChannel(
            self._support.registry,
            self._events,
            self._pause,
            self.shape,
            self._timeouts.max_total,
        )

    async def _pause(self, mode: str = "parked", upstream_state: str | None = None) -> str:
        """Seal the state the client's retry must echo, and tell the chain the leg waits."""
        cipher = self._support.state_cipher
        if cipher is None:
            raise RelayRejected(NO_CIPHER)
        assert self._timeouts is not None
        expires_at = time.time() + self._timeouts.max_total
        state = RequestState(
            correlation_id=self._correlation_id,
            mode=mode,  # type: ignore[arg-type]
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
            # only capabilities the client advertised are offered upstream
            client_capabilities=self._ctx.client_capabilities,
            log_level=self._ctx.log_level,
            relay=relay,
            handle=self._handle,
            timeouts=self._timeouts,
            on_progress=on_progress,
            raw_input_required=self._ctx.era is ProtocolEra.STATELESS,
            resume=self._resume,
        )

    def _release(self) -> None:
        if self._handle is not None:
            self._support.registry.unregister_call(self._handle)
            self._handle = None

    async def finish(self, outcome: CallOutcome, started: float) -> None:
        """Account for the call: release the handle and tell every stage how it ended."""
        self._release()
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
