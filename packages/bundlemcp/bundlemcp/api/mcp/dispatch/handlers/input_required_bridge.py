"""Multi Round-Trip Requests for the reads a modern client makes of a bundle's members."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import Response
from fastapi.responses import JSONResponse
from fastmcp import Client
from mcp.types import INVALID_PARAMS, InputRequiredResult, InputResponses
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error
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
    StateRejected,
    arguments_digest,
    input_required_result,
)
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.servers.mcp_server import McpServer

log = structlog.get_logger(__name__)

NO_CIPHER = "input_required is unavailable on this gateway: no token encryption keys configured"
TERMINAL_PHASES = ("input_required", "result")
UPSTREAM_FAILURE = -32000

input_responses_adapter: TypeAdapter[InputResponses] = TypeAdapter(InputResponses)

# Sends the read to one member: the client, the retry's answers and the
# member's own requestState, both None on a first request.
MemberRead = Callable[[Client, InputResponses | None, str | None], Awaitable[Any]]
# The error member of the message when no member gave a result: the member
# last tried and what it raised, both None when there was none to try.
ReadFailure = Callable[[McpServer | None, Exception | None], dict[str, Any]]


class BridgedRead(BaseModel):
    """One read as the bridge drives it: what it names, who may answer, how it renders."""

    model_config = ConfigDict(frozen=True)

    ctx: RequestContext = Field(description="The admitted request the read belongs to")
    message: JsonRpcMessage = Field(
        description="The client's request, whose id the answer carries and whose params hold a "
        "retry's requestState and inputResponses"
    )
    target: str = Field(
        description="What the read names: the presented prompt name, or the resource URI"
    )
    arguments: dict[str, Any] = Field(
        description="The read's arguments, which a sealed state is bound to; empty for a "
        "resource read"
    )
    members: list[McpServer] = Field(
        description="The members that may answer, asked in this order until one does"
    )
    read: MemberRead = Field(description="Sends the read to one member")
    render: Callable[[Any], dict[str, Any]] = Field(
        description="Turns a member's result into the result payload the client receives"
    )
    failed: ReadFailure = Field(
        description="The error the client receives when no member gave a result"
    )

    @property
    def method(self) -> str:
        """The method being read, as the client's request names it."""
        return self.message.method or ""


class InputRequiredBridge:
    """Answers a modern client's read with ``input_required`` when a member needs input.

    A modern member's own ``input_required`` is passed through, its state
    sealed inside the gateway's; the retry re-issues the read to the same
    member with the answers. A handshake member's request for input parks the
    read on this replica until the client's retry, served by any replica,
    routes the answers here over the signal bus; if no replica claims them the
    read is re-run with the answers given as the member asks again. Reads are
    neither metered nor audited, and are answered as one JSON message.
    """

    def __init__(
        self,
        fanout: MemberFanout,
        registry: StreamRegistry,
        signals: SignalBus,
        runtime_config: RuntimeConfig,
        cipher: SecretCipher | None,
        *,
        resume_grace: float = 2.0,
    ) -> None:
        self._fanout = fanout
        self._registry = registry
        self._signals = signals
        self._runtime_config = runtime_config
        self._cipher = cipher
        self._resume_grace = resume_grace
        self._detached: set[asyncio.Task[None]] = set()

    async def serve(self, read: BridgedRead) -> Response:
        token = read.message.param("requestState")
        if token is None:
            return await self._start(read, channel=None, responses=None, state=None)
        if self._cipher is None:
            return rpc_error(read.message.id, UPSTREAM_FAILURE, NO_CIPHER)
        try:
            state = RequestState.unseal(
                self._cipher,
                token,
                method=read.method,
                target=read.target,
                arguments=read.arguments,
                sub=read.ctx.identity.sub,
            )
            responses = read.message.param("inputResponses", {})
            input_responses_adapter.validate_python(responses)
        except StateRejected as exc:
            return rpc_error(read.message.id, INVALID_PARAMS, str(exc), status=400)
        except ValidationError as exc:
            return rpc_error(
                read.message.id, INVALID_PARAMS, f"invalid inputResponses: {exc}", status=400
            )
        if state.mode == "passthrough":
            return await self._start(read, channel=None, responses=responses, state=state)
        return await self._resume(read, state, responses)

    async def _start(
        self,
        read: BridgedRead,
        *,
        channel: InputChannel | None,
        responses: dict[str, Any] | None,
        state: RequestState | None,
    ) -> Response:
        """Run the read detached, and answer with the first thing it has for the client."""
        timeouts = await self._runtime_config.call_timeouts()
        correlation_id = state.correlation_id if state is not None else uuid.uuid4().hex
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        events = CallEvents(correlation_id, queue, self._signals)

        def seal(mode: RelayMode, member: str | None, upstream_state: str | None) -> str:
            if self._cipher is None:
                raise RelayRejected(NO_CIPHER)
            return RequestState(
                correlation_id=correlation_id,
                mode=mode,
                method=read.method,
                target=read.target,
                arguments_digest=arguments_digest(read.arguments),
                sub=read.ctx.identity.sub,
                member=member,
                expires_at=time.time() + timeouts.max_total,
                upstream_state=upstream_state,
            ).seal(self._cipher)

        async def seal_parked() -> str:
            return seal("parked", None, None)

        if channel is None and state is None:
            channel = ParkingChannel(
                self._registry, events, seal_parked, read.ctx.shape, timeouts.max_total
            )
        members = read.members
        if state is not None and state.member is not None:
            members = [m for m in members if m.name == state.member]

        async def run() -> None:
            try:
                async with asyncio.timeout(timeouts.max_total):
                    await self._read(read, members, events, channel, responses, state, seal)
            except TimeoutError:
                await events.emit("result", {"error": _upstream_error("max_total_timeout")})
            except Exception:
                log.warning("mrtr.read_failed", method=read.method, exc_info=True)
                await events.emit("result", {"error": _upstream_error("read failed")})

        task = asyncio.create_task(run())
        self._detached.add(task)
        task.add_done_callback(self._detached.discard)
        phase, payload = await _terminal(queue)
        return JSONResponse({"jsonrpc": "2.0", "id": read.message.id, **payload})

    async def _read(
        self,
        read: BridgedRead,
        members: list[McpServer],
        events: CallEvents,
        channel: InputChannel | None,
        responses: dict[str, Any] | None,
        state: RequestState | None,
        seal: Callable[[RelayMode, str | None, str | None], str],
    ) -> None:
        answers = (
            input_responses_adapter.validate_python(responses)
            if responses is not None and state is not None and state.mode == "passthrough"
            else None
        )
        upstream_state = state.upstream_state if state is not None else None
        last: tuple[McpServer | None, Exception | None] = (None, None)
        for server in members:
            try:
                async with self._fanout.lease(read.ctx, server, channel=channel) as lease:
                    result = await read.read(lease.client, answers, upstream_state)
            except Exception as exc:
                log.warning("passthrough.member_failed", server=server.name)
                last = (server, exc)
                continue
            if isinstance(result, InputRequiredResult):
                try:
                    sealed = seal("passthrough", server.name, result.request_state)
                except RelayRejected as exc:
                    await events.emit("result", {"error": _upstream_error(str(exc))})
                    return
                requests = result.model_dump(by_alias=True, mode="json", exclude_none=True)[
                    "inputRequests"
                ]
                asked = input_required_result(requests, sealed)
                await events.emit("input_required", {"result": read.ctx.shape(asked)})
                return
            await events.emit("result", {"result": read.render(result)})
            return
        await events.emit("result", {"error": read.failed(*last)})

    async def _resume(
        self, read: BridgedRead, state: RequestState, responses: dict[str, Any]
    ) -> Response:
        """Hand the answers to the parked read and answer with what it says next."""
        queue = self._registry.register_resume(state.correlation_id)
        try:
            await self._signals.reply(state.correlation_id, {"result": responses})
            try:
                first = await asyncio.wait_for(queue.get(), timeout=self._resume_grace)
            except TimeoutError:
                # the parking replica is gone; re-run so the client still gets a result.
                log.warning("mrtr.park_lost", method=read.method, sub=read.ctx.identity.sub)
                return await self._start(
                    read, channel=PreansweredChannel(responses), responses=responses, state=state
                )
            timeouts = await self._runtime_config.call_timeouts()
            async with asyncio.timeout(timeouts.max_total):
                phase, payload = await _terminal(queue, first=first)
        finally:
            self._registry.unregister_resume(state.correlation_id, queue)
        return JSONResponse({"jsonrpc": "2.0", "id": read.message.id, **payload})


async def _terminal(
    queue: asyncio.Queue, *, first: tuple[str, Any] | None = None
) -> tuple[str, dict[str, Any]]:
    """The next event that ends this response: a request for input or the result."""
    while True:
        phase, payload = first if first is not None else await queue.get()
        first = None
        if phase in TERMINAL_PHASES:
            return phase, payload


def _upstream_error(message: str) -> dict[str, Any]:
    return {"code": UPSTREAM_FAILURE, "message": message}
