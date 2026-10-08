"""A billing service as the metering hook, over HTTP, end to end through the gateway (MID-6).

The billing service is an httpx MockTransport stub; the gateway, its upstreams
and its sessions are the same hermetic stack test_gateway.py runs.
"""

import asyncio
import json

import httpx
import pytest
from bundlemcp.infrastructure.metering.http_metering_hook import HttpMeteringHook

from tests.api.test_gateway import _initialize, _rpc, _running, upstream_factory
from tests.conftest import hermetic_settings

BILLING_URL = "http://billing.test/meter"
SAY = {"name": "echo__say", "arguments": {"text": "x"}}


class BillingStub:
    """Answers pre-calls as told and records every event it receives."""

    def __init__(self) -> None:
        self.pre_answer: str = "allow"
        self.post_failures = 0  # post-calls answered 503 before one is acknowledged
        self.events: list[dict] = []
        self.authorization: list[str | None] = []

    @property
    def pre_calls(self) -> list[dict]:
        return [e for e in self.events if e["event"] == "pre_call"]

    @property
    def post_calls(self) -> list[dict]:
        return [e for e in self.events if e["event"] == "post_call"]

    async def handler(self, request: httpx.Request) -> httpx.Response:
        event = json.loads(request.content)
        self.events.append(event)
        self.authorization.append(request.headers.get("authorization"))
        if event["event"] == "post_call":
            if self.post_failures:
                self.post_failures -= 1
                return httpx.Response(503)
            return httpx.Response(204)
        match self.pre_answer:
            case "allow":
                return httpx.Response(200, json={"allowed": True})
            case "deny":
                return httpx.Response(
                    200,
                    json={
                        "allowed": False,
                        "reason": "insufficient_credits",
                        "user_message": "Your credits are used up. Top up at https://x.test/b",
                    },
                )
            case "timeout":
                await asyncio.sleep(5)
                return httpx.Response(200, json={"allowed": True})
            case "500":
                return httpx.Response(500)
            case "garbage":
                return httpx.Response(200, json={"allowed": "yes"})
            case "unreachable":
                raise httpx.ConnectError("connection refused", request=request)
        raise AssertionError(self.pre_answer)


class CountingUpstreams:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, server, extra_headers, **kwargs):
        self.calls += 1
        return upstream_factory(server, extra_headers, **kwargs)


async def _no_wait(_seconds: float) -> None:
    return None


@pytest.fixture
async def billing(engine, redis):
    stub = BillingStub()
    hook = HttpMeteringHook(
        BILLING_URL,
        token="billing-token",
        timeout=0.2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(stub.handler)),
        sleep=_no_wait,
    )
    upstreams = CountingUpstreams()
    async with _running(engine, redis, metering_hook=hook, client_factory=upstreams) as (
        http,
        _app,
    ):
        yield http, stub, upstreams, hook
    await hook.aclose()


async def _settled(hook: HttpMeteringHook) -> None:
    """Wait for the post-calls the hook is still delivering in the background."""
    async with asyncio.timeout(5):
        while hook._deliveries:
            await asyncio.sleep(0.01)


async def test_one_pre_call_per_tools_call_and_none_for_listing(billing):
    """MID-6 (#89): initialize and tools/list are not metered; tools/call is, once."""
    http, stub, upstreams, hook = billing
    session = await _initialize(http)
    await _rpc(http, "main", session, "tools/list")
    assert stub.events == []

    resp = await _rpc(http, "main", session, "tools/call", SAY)
    assert resp.json()["result"]["content"][0]["text"] == "echo:x"
    await _settled(hook)

    (pre,) = stub.pre_calls
    (post,) = stub.post_calls
    assert pre["protocol_version"] == 2
    assert pre["context"]["tool"] == "say" and pre["context"]["bundle"] == "main"
    assert {"oidc_issuer", "oidc_sub", "server", "idempotency_key"} <= pre["context"].keys()
    assert post["outcome"] == "result"
    assert post["context"]["idempotency_key"] == pre["context"]["idempotency_key"]
    assert set(stub.authorization) == {"Bearer billing-token"}


async def test_deny_message_reaches_the_client_verbatim(billing):
    """MID-3 (#89): the hook's user_message is the tool's error result; nothing runs upstream."""
    http, stub, upstreams, hook = billing
    stub.pre_answer = "deny"
    session = await _initialize(http)

    result = (await _rpc(http, "main", session, "tools/call", SAY)).json()["result"]

    assert result["isError"] is True
    assert result["content"] == [
        {"type": "text", "text": "Your credits are used up. Top up at https://x.test/b"}
    ]
    assert upstreams.calls == 0
    await _settled(hook)
    assert stub.post_calls == []  # an answered denial debited nothing


@pytest.mark.parametrize("answer", ["timeout", "500", "unreachable", "garbage"])
async def test_unanswered_pre_call_denies_and_compensates(billing, answer):
    """MID-6 (#89): no usable answer denies the call without the upstream, posts no_result
    under the same key, and leaves the session working."""
    http, stub, upstreams, hook = billing
    stub.pre_answer = answer
    session = await _initialize(http)

    resp = await _rpc(http, "main", session, "tools/call", SAY)

    assert resp.json()["error"]["message"] == "metering_unavailable"
    assert upstreams.calls == 0
    await _settled(hook)
    (pre,) = stub.pre_calls
    (post,) = stub.post_calls
    assert post["outcome"] == "no_result" and post["duration_ms"] == 0
    assert post["context"]["idempotency_key"] == pre["context"]["idempotency_key"]
    assert (await _rpc(http, "main", session, "ping")).status_code == 200


async def test_post_call_is_retried_until_acknowledged(billing):
    """MID-6 (#89): a post-call the billing service fails to take is delivered again."""
    http, stub, upstreams, hook = billing
    stub.post_failures = 3
    session = await _initialize(http)

    await _rpc(http, "main", session, "tools/call", SAY)
    await _settled(hook)

    assert len(stub.post_calls) == 4
    assert len({p["context"]["idempotency_key"] for p in stub.post_calls}) == 1


async def test_http_hook_and_in_process_hook_are_exclusive():
    """MID-6: one metering hook per deployment."""
    with pytest.raises(ValueError, match="not both"):
        hermetic_settings(metering_hook="x:y", metering_http_url=BILLING_URL)
