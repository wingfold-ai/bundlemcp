"""A metering hook that runs out of process, reached over HTTP."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
import structlog
from pydantic import ValidationError

from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.metering.meter_decision import MeterDecision
from bundlemcp.application.metering.meter_outcome import MeterOutcome
from bundlemcp.infrastructure.metering.metering_event import PostCallEvent, PreCallEvent

log = structlog.get_logger(__name__)

Sleep = Callable[[float], Awaitable[None]]

# PROT-29: a post-call is tried five times within about a minute: the waits
# between tries, plus up to one timeout per try.
POST_CALL_RETRY_DELAYS = (1.0, 3.0, 9.0, 27.0)
# How long shutdown waits for post-calls still being delivered.
DRAIN_SECONDS = 5.0


class MeteringServiceError(Exception):
    """The hook service gave no answer the gateway can act on."""


class HttpMeteringHook:
    """POSTs a pre-call and a post-call event for every metered tool call.

    A pre-call that times out, cannot be sent, is answered with a non-2xx
    status or with a body that is not a decision raises, so the gateway's
    failure policy decides the call. A post-call is delivered in the
    background, so the tool result never waits for the hook, and retried with
    backoff on a transport error, a 429 or a 5xx; any other answer is final.
    """

    def __init__(
        self,
        url: str,
        *,
        token: str | None,
        timeout: float,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._url = url
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._timeout = timeout
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._sleep = sleep
        self._deliveries: set[asyncio.Task[None]] = set()

    async def pre_call(self, ctx: MeterContext) -> MeterDecision:
        try:
            response = await self._post(PreCallEvent(context=ctx).model_dump_json())
        except (httpx.HTTPError, TimeoutError) as exc:
            raise MeteringServiceError("metering hook did not answer the pre-call") from exc
        if not response.is_success:
            raise MeteringServiceError(f"metering hook answered {response.status_code}")
        try:
            return MeterDecision.model_validate_json(response.content, strict=True)
        except ValidationError as exc:
            raise MeteringServiceError("metering hook answered with no decision") from exc

    async def post_call(self, ctx: MeterContext, outcome: MeterOutcome, duration_ms: int) -> None:
        event = PostCallEvent(context=ctx, outcome=outcome, duration_ms=duration_ms)
        task = asyncio.create_task(self._deliver(event))
        self._deliveries.add(task)
        task.add_done_callback(self._deliveries.discard)

    async def aclose(self) -> None:
        """Give post-calls in flight a moment to land, then stop."""
        if self._deliveries:
            _, pending = await asyncio.wait(self._deliveries, timeout=DRAIN_SECONDS)
            for task in pending:
                task.cancel()
            if pending:
                log.error("metering.post_call_abandoned", count=len(pending))
        await self._client.aclose()

    async def _deliver(self, event: PostCallEvent) -> None:
        key = event.context.idempotency_key
        for attempt, delay in enumerate((*POST_CALL_RETRY_DELAYS, None), start=1):
            try:
                response = await self._post(event.model_dump_json())
            except (httpx.HTTPError, TimeoutError):
                retryable, status = True, None
            else:
                if response.is_success:
                    return
                status = response.status_code
                retryable = status == 429 or status >= 500
            if not retryable or delay is None:
                break
            log.warning("metering.post_call_retry", attempt=attempt, status=status)
            await self._sleep(delay)
        # The key is what the hook service reconciles on; it is not a secret.
        log.error(
            "metering.post_call_failed", idempotency_key=key, outcome=event.outcome, status=status
        )

    async def _post(self, body: str) -> httpx.Response:
        async with asyncio.timeout(self._timeout):
            return await self._client.post(
                self._url,
                content=body,
                headers={**self._headers, "Content-Type": "application/json"},
            )
