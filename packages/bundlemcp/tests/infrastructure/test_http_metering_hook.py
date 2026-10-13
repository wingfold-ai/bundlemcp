"""The HTTP metering hook's delivery rules, against an httpx MockTransport (PROT-29)."""

import httpx
from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.metering.meter_outcome import MeterOutcome
from bundlemcp.infrastructure.metering.http_metering_hook import (
    POST_CALL_RETRY_DELAYS,
    HttpMeteringHook,
)

CTX = MeterContext(
    sub="api_key:1",
    email=None,
    oidc_issuer=None,
    oidc_sub=None,
    endpoint="main",
    bundle="main",
    server="echo",
    tool="say",
    idempotency_key="k1",
)


def _hook(answer: httpx.Response | Exception, waits: list[float]) -> tuple[HttpMeteringHook, list]:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def record_wait(seconds: float) -> None:
        waits.append(seconds)

    hook = HttpMeteringHook(
        "http://metering.test/hook",
        token=None,
        timeout=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        sleep=record_wait,
    )
    return hook, sent


async def test_post_call_gives_up_after_five_tries():
    """PROT-29: a hook service that never takes the post-call is tried five times, then
    the failure is logged with the key to reconcile on."""
    waits: list[float] = []
    hook, sent = _hook(httpx.ConnectError("refused"), waits)
    await hook.post_call(CTX, MeterOutcome.NO_RESULT, 0)
    await hook.aclose()
    assert len(sent) == 5
    assert waits == list(POST_CALL_RETRY_DELAYS)
    assert sum(waits) < 60


async def test_post_call_rejected_by_the_service_is_not_retried():
    """PROT-29: a 4xx other than 429 is an answer, not a transport failure."""
    waits: list[float] = []
    hook, sent = _hook(httpx.Response(400), waits)
    await hook.post_call(CTX, MeterOutcome.RESULT, 12)
    await hook.aclose()
    assert len(sent) == 1 and waits == []


async def test_post_call_does_not_wait_for_delivery():
    """PROT-29: the tool result never waits for the hook; shutdown drains what is in flight."""
    waits: list[float] = []
    hook, sent = _hook(httpx.Response(204), waits)
    await hook.post_call(CTX, MeterOutcome.TOOL_ERROR, 5)
    assert sent == []  # queued, not yet sent
    await hook.aclose()
    assert len(sent) == 1
    assert b'"outcome":"tool_error"' in sent[0].content
