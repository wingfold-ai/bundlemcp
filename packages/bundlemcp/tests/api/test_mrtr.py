"""Multi Round-Trip Requests for modern-era clients (PROT-18, SES-16).

A modern client cannot be sent a server-initiated request, so an upstream's
request for input becomes an ``input_required`` result the client answers by
retrying. Against a modern upstream the gateway passes the upstream's own
result through; against a handshake upstream it parks the call and resumes it
from whichever replica serves the retry.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from bundlemcp.api.mcp.relay import RequestState, arguments_digest
from bundlemcp.application.metering.invocation_sweeper import InvocationSweeper
from bundlemcp.application.metering.meter_decision import MeterDecision
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.shared.secrets import (
    API_KEY_PREFIX,
    display_prefix,
    generate_token,
    hash_token,
)
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.fastmcp.connect_mode import connect_mode
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.valkey.paused_invocations import ValkeyPausedInvocations
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides
from cryptography.fernet import Fernet
from fakeredis.aioredis import FakeRedis
from fastmcp import Client, Context, FastMCP
from httpx import AsyncClient
from mcp.shared.inbound import NAME_BEARING_METHODS
from mcp.types import (
    CLIENT_CAPABILITIES_META_KEY,
    INVALID_PARAMS,
    PROTOCOL_VERSION_META_KEY,
    ElicitRequest,
    ElicitRequestFormParams,
    InputRequiredResult,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

from tests.api.test_relay import running_app

KEY = Fernet.generate_key().decode()
ENDPOINT_KEY = generate_token(API_KEY_PREFIX)
OTHER_KEY = generate_token(API_KEY_PREFIX)
MODERN = "2026-07-28"
CAPS = {"elicitation": {}}

# --- a handshake-era upstream that asks with server-initiated requests ------------

legacy_up = FastMCP("legacyup")


@legacy_up.tool
async def ask_name(ctx: Context) -> str:
    """One elicitation."""
    result = await ctx.elicit("What is your name?", response_type=str)
    return f"hello {result.data}" if result.action == "accept" else "declined"


@legacy_up.tool
async def ask_twice(ctx: Context) -> str:
    """Two elicitations in one call."""
    first = await ctx.elicit("First?", response_type=str)
    second = await ctx.elicit("Second?", response_type=str)
    return f"{first.data}+{second.data}"


# --- a modern upstream that asks with input_required (guard pattern) -------------

modern_up = FastMCP("modernup")


@modern_up.tool(name="ask_name")
async def modern_ask_name(ctx: Context) -> InputRequiredResult | str:
    """One input_required round."""
    answer = (ctx.input_responses or {}).get("name")
    if answer is not None and answer.action == "accept":
        return f"hi {answer.content['value']}"
    return InputRequiredResult(
        input_requests={
            "name": ElicitRequest(
                params=ElicitRequestFormParams(
                    message="What is your name?",
                    requested_schema={
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                    },
                )
            )
        },
        request_state="upstream-state-1",
    )


@legacy_up.resource("note://secret")
async def secret_note(ctx: Context) -> str:
    """A resource served only after the reader answers."""
    result = await ctx.elicit("Password?", response_type=str)
    return f"note for {result.data}" if result.action == "accept" else "declined"


@modern_up.prompt(name="greeting")
async def modern_greeting(ctx: Context) -> InputRequiredResult | str:
    """A prompt rendered only after the client says who it greets."""
    answer = (ctx.input_responses or {}).get("who")
    if answer is not None and answer.action == "accept":
        return f"Greet {answer.content['value']}"
    return InputRequiredResult(
        input_requests={
            "who": ElicitRequest(
                params=ElicitRequestFormParams(
                    message="Whom to greet?",
                    requested_schema={
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                    },
                )
            )
        },
        request_state="prompt-state-1",
    )


UPSTREAMS = {"legacyup": legacy_up, "modernup": modern_up}


def upstream_factory(server, extra_headers, *, observer=None, **handlers):
    return Client(UPSTREAMS[server.name], mode=connect_mode(server.protocol_mode), **handlers)


class RecordingHook:
    def __init__(self) -> None:
        self.pre: list[str] = []
        self.post: list[str] = []
        self.contexts: list = []

    async def pre_call(self, ctx) -> MeterDecision:
        self.pre.append(ctx.idempotency_key)
        self.contexts.append(ctx)
        return MeterDecision(allowed=True, scratch={"reservation": f"r-{len(self.pre)}"})

    async def post_call(self, ctx, outcome, duration_ms) -> None:
        self.post.append(outcome)
        self.contexts.append(ctx)


async def seed(engine: AsyncEngine) -> dict[str, str]:
    """Seed and return the caller subjects of the two endpoint keys."""
    factory = session_factory(engine)
    async with factory() as db:
        keys = [
            ApiKeyRow(
                name=name,
                key_hash=hash_token(token),
                key_prefix=display_prefix(token),
                kind=ApiKeyKind.ENDPOINT,
            )
            for name, token in (("k1", ENDPOINT_KEY), ("k2", OTHER_KEY))
        ]
        legacy = McpServerRow(
            name="legacyup",
            url="http://legacyup/mcp",
            protocol_mode="legacy",
            capabilities={"tools": {}, "resources": {}},
        )
        modern = McpServerRow(
            name="modernup", url="http://modernup/mcp", capabilities={"tools": {}, "prompts": {}}
        )
        bundle = BundleRow(name="main")
        db.add_all([*keys, legacy, modern, bundle])
        await db.commit()
        for obj in (*keys, legacy, modern, bundle):
            await db.refresh(obj)
        db.add_all(
            [
                BundleServerRow(bundle_id=bundle.id, server_id=legacy.id),
                BundleServerRow(bundle_id=bundle.id, server_id=modern.id),
                EndpointRow(name="main", bundle_id=bundle.id, auth_modes=["api_key"]),
                ToolRow(server_id=legacy.id, name="ask_name", schema_hash="h", input_schema={}),
                ToolRow(server_id=legacy.id, name="ask_twice", schema_hash="h", input_schema={}),
                ToolRow(server_id=modern.id, name="ask_name", schema_hash="h", input_schema={}),
            ]
        )
        await db.commit()
        return {
            "k1": CallerIdentity.with_api_key(keys[0].id).sub,
            "k2": CallerIdentity.with_api_key(keys[1].id).sub,
        }


def make_app(engine, redis, hook, *, keys=(KEY,)):
    settings = EnvSettings(
        _env_file=None, database_url="sqlite+aiosqlite://", token_encryption_keys=list(keys)
    )
    return create_app(
        settings,
        overrides=CompositionOverrides(
            engine=engine, redis=redis, client_factory=upstream_factory, metering_hook=hook
        ),
    )


@pytest.fixture
async def env(engine: AsyncEngine, redis: FakeRedis):
    subs = await seed(engine)
    hook = RecordingHook()
    app = make_app(engine, redis, hook)
    async with running_app(app) as base_url:
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http:
            yield http, app, hook, subs, base_url


def _modern(method, params=None, *, id_=1):
    params = dict(params or {})
    params["_meta"] = {PROTOCOL_VERSION_META_KEY: MODERN, CLIENT_CAPABILITIES_META_KEY: CAPS}
    headers = {"MCP-Protocol-Version": MODERN, "Mcp-Method": method}
    if method in NAME_BEARING_METHODS:
        headers["Mcp-Name"] = params[NAME_BEARING_METHODS[method]]
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}, headers


async def _read(http, method, params, *, id_=1):
    """POST a modern prompts/get or resources/read and return the JSON-RPC message."""
    body, headers = _modern(method, params, id_=id_)
    resp = await http.post("/main/mcp", headers=headers, json=body)
    return resp.status_code, resp.json()


async def _call(http, name, arguments=None, *, id_=1, **extra):
    """POST a modern tools/call and return the final JSON-RPC message (from SSE or JSON)."""
    body, headers = _modern(
        "tools/call", {"name": name, "arguments": arguments or {}, **extra}, id_=id_
    )
    async with http.stream("POST", "/main/mcp", headers=headers, json=body) as resp:
        if not resp.headers["content-type"].startswith("text/event-stream"):
            return resp.status_code, json.loads(await resp.aread())
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                msg = json.loads(line[6:])
                if msg.get("id") == id_:
                    return resp.status_code, msg
    raise AssertionError("stream ended without a final message")


def _accept(value: str) -> dict:
    return {"action": "accept", "content": {"value": value}}


async def _audit_statuses(app) -> list[str]:
    await app.state.container.audit.drain()
    async with app.state.container.session_factory() as db:
        return sorted(r.status for r in (await db.execute(select(AuditRecordRow))).scalars())


async def test_passthrough_forwards_the_upstreams_input_required(env):
    """PROT-18, PROT-26 passthrough: modern client, modern upstream, charged once."""
    http, app, hook, subs, base_url = env
    status, first = await _call(http, "modernup__ask_name")
    assert status == 200
    result = first["result"]
    assert result["resultType"] == "input_required"
    assert result["inputRequests"]["name"]["method"] == "elicitation/create"
    assert "upstream-state-1" not in result["requestState"]  # sealed, not echoed in clear

    status, final = await _call(
        http,
        "modernup__ask_name",
        id_=2,
        inputResponses={"name": _accept("Ada")},
        requestState=result["requestState"],
    )
    assert final["result"]["content"][0]["text"] == "hi Ada"
    assert final["result"]["resultType"] == "complete"
    # both legs are one invocation to the hook: asked on the first, told on the last
    assert len(hook.pre) == 1
    assert hook.post == ["result"]
    assert await _audit_statuses(app) == ["input_required", "success"]


async def test_prot24_prot26_a_paused_invocation_keeps_its_context_across_legs(env):
    """PROT-24, PROT-26: a modern request has no session, and the post_call of the retry
    carries the scratch the first leg's pre_call left."""
    http, app, hook, subs, base_url = env
    status, first = await _call(http, "modernup__ask_name")
    status, final = await _call(
        http,
        "modernup__ask_name",
        id_=2,
        inputResponses={"name": _accept("Ada")},
        requestState=first["result"]["requestState"],
    )
    assert final["result"]["resultType"] == "complete"
    pre_ctx, post_ctx = hook.contexts
    assert pre_ctx.session_id is None
    assert post_ctx.idempotency_key == pre_ctx.idempotency_key
    assert post_ctx.scratch == {"reservation": "r-1"}


def _sweeper(redis, hook, *, after: float) -> InvocationSweeper:
    """A sweeper whose clock reads ``after`` seconds from now."""
    later = datetime.now(UTC) + timedelta(seconds=after)
    return InvocationSweeper(
        ValkeyPausedInvocations(redis, clock=SystemClock()), hook, ManualClock(later)
    )


async def test_prot26_an_abandoned_invocation_is_closed_once(env, redis):
    """PROT-26: a call that paused for input and was never retried gets exactly one post_call
    no_result once its requestState has expired."""
    http, app, hook, subs, base_url = env
    status, first = await _call(http, "modernup__ask_name")
    assert first["result"]["resultType"] == "input_required"
    assert hook.post == []

    assert await _sweeper(redis, hook, after=0).sweep() == 0  # not yet expired
    sweeper = _sweeper(redis, hook, after=3600)
    assert await sweeper.sweep() == 1
    assert await sweeper.sweep() == 0
    assert hook.post == ["no_result"]
    assert hook.contexts[-1].idempotency_key == hook.pre[0]


async def test_prot26_a_retry_before_the_sweep_leaves_nothing_to_close(env, redis):
    """PROT-26: once a retry has settled the invocation, the expiry sweep reports nothing more."""
    http, app, hook, subs, base_url = env
    status, first = await _call(http, "modernup__ask_name")
    await _call(
        http,
        "modernup__ask_name",
        id_=2,
        inputResponses={"name": _accept("Ada")},
        requestState=first["result"]["requestState"],
    )
    assert await _sweeper(redis, hook, after=3600).sweep() == 0
    assert hook.post == ["result"]


async def test_parked_call_resumes_on_another_replica(env, engine, redis):
    """PROT-18 park and resume: the retry lands on replica B, the call waits on A."""
    http_a, app_a, hook, subs, base_a = env
    status, first = await _call(http_a, "legacyup__ask_name")
    assert "result" in first, first
    assert first["result"]["resultType"] == "input_required"
    (key, request), *_ = first["result"]["inputRequests"].items()
    assert request["method"] == "elicitation/create"

    app_b = make_app(engine, redis, hook)
    async with running_app(app_b) as base_b:
        async with AsyncClient(
            base_url=base_b, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http_b:
            status, final = await _call(
                http_b,
                "legacyup__ask_name",
                id_=2,
                inputResponses={key: _accept("Grace")},
                requestState=first["result"]["requestState"],
            )
    assert final["result"]["content"][0]["text"] == "hello Grace"
    assert len(hook.pre) == 1 and hook.post == ["result"]  # one invocation, charged once
    assert await _audit_statuses(app_a) == ["success"]


async def test_parked_call_asks_again_for_a_second_round(env):
    http, app, hook, subs, base_url = env
    status, first = await _call(http, "legacyup__ask_twice")
    (key1, _), *_ = first["result"]["inputRequests"].items()
    status, second = await _call(
        http,
        "legacyup__ask_twice",
        id_=2,
        inputResponses={key1: _accept("a")},
        requestState=first["result"]["requestState"],
    )
    assert second["result"]["resultType"] == "input_required"
    (key2, _), *_ = second["result"]["inputRequests"].items()
    assert key2 != key1
    status, final = await _call(
        http,
        "legacyup__ask_twice",
        id_=3,
        inputResponses={key2: _accept("b")},
        requestState=second["result"]["requestState"],
    )
    assert final["result"]["content"][0]["text"] == "a+b"


async def test_tampered_or_foreign_state_is_rejected(env):
    """PROT-18: requestState is integrity-protected and bound to the caller."""
    http, app, hook, subs, base_url = env
    status, first = await _call(http, "modernup__ask_name")
    state = first["result"]["requestState"]

    tampered = state[:-4] + ("AAAA" if state[-4:] != "AAAA" else "BBBB")
    status, resp = await _call(
        http,
        "modernup__ask_name",
        id_=2,
        inputResponses={"name": _accept("x")},
        requestState=tampered,
    )
    assert status == 400 and resp["error"]["code"] == INVALID_PARAMS

    async with AsyncClient(
        base_url=base_url, headers={"Authorization": f"Bearer {OTHER_KEY}"}, timeout=10
    ) as other:
        status, resp = await _call(
            other,
            "modernup__ask_name",
            id_=3,
            inputResponses={"name": _accept("x")},
            requestState=state,
        )
    assert status == 400 and "another caller" in resp["error"]["message"]

    status, resp = await _call(
        http,
        "modernup__ask_name",
        {"extra": 1},
        id_=4,
        inputResponses={"name": _accept("x")},
        requestState=state,
    )
    assert status == 400 and "different call" in resp["error"]["message"]


async def test_lost_park_falls_back_to_a_rerun(env):
    """SES-16: no replica claims the answers, so the call is re-run with them pre-loaded."""
    http, app, hook, subs, base_url = env
    cipher = app.state.container.token_cipher
    state = RequestState(
        correlation_id="nobody-holds-this",
        mode="parked",
        presented_tool="legacyup__ask_name",
        arguments_digest=arguments_digest({}),
        sub=subs["k1"],
        idempotency_key="carried-over",
        expires_at=4102444800.0,
    ).seal(cipher)
    status, final = await _call(
        http, "legacyup__ask_name", inputResponses={"input-1": _accept("Linus")}, requestState=state
    )
    assert final["result"]["content"][0]["text"] == "hello Linus"
    assert hook.pre == ["carried-over"] and hook.post == ["result"]


async def test_input_required_is_unavailable_without_encryption_keys(engine, redis):
    """PROT-18: without a cipher the gateway refuses rather than sealing plaintext."""
    await seed(engine)
    app = make_app(engine, redis, RecordingHook(), keys=())
    async with running_app(app) as base_url:
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http:
            status, through = await _call(http, "modernup__ask_name")
            assert "unavailable" in through["error"]["message"]
            status, parked = await _call(http, "legacyup__ask_name", id_=2)
            assert parked["result"]["isError"] is True
    await asyncio.sleep(0)


async def test_prot18_prompt_needs_input_from_a_modern_member(env):
    """PROT-18: a modern member's input_required on prompts/get reaches the client, and the
    retry renders the prompt; prompts are not metered."""
    http, app, hook, subs, base_url = env
    status, first = await _read(http, "prompts/get", {"name": "modernup__greeting"})
    result = first["result"]
    assert result["resultType"] == "input_required"
    assert result["inputRequests"]["who"]["method"] == "elicitation/create"
    assert "prompt-state-1" not in result["requestState"]

    status, final = await _read(
        http,
        "prompts/get",
        {
            "name": "modernup__greeting",
            "inputResponses": {"who": _accept("Ada")},
            "requestState": result["requestState"],
        },
        id_=2,
    )
    assert final["result"]["resultType"] == "complete"
    assert final["result"]["messages"][0]["content"]["text"] == "Greet Ada"
    assert hook.pre == [] and hook.post == []


async def test_prot18_resource_read_needs_input_from_a_handshake_member(env, engine, redis):
    """PROT-18: a handshake member's elicitation during resources/read parks the read; the
    retry, served by another replica, returns the contents."""
    http_a, app_a, hook, subs, base_a = env
    status, first = await _read(http_a, "resources/read", {"uri": "note://secret"})
    assert first["result"]["resultType"] == "input_required", first
    (key, request), *_ = first["result"]["inputRequests"].items()
    assert request["method"] == "elicitation/create"

    app_b = make_app(engine, redis, hook)
    async with running_app(app_b) as base_b:
        async with AsyncClient(
            base_url=base_b, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http_b:
            status, final = await _read(
                http_b,
                "resources/read",
                {
                    "uri": "note://secret",
                    "inputResponses": {key: _accept("Grace")},
                    "requestState": first["result"]["requestState"],
                },
                id_=2,
            )
    assert final["result"]["contents"][0]["text"] == "note for Grace"
    assert hook.pre == [] and hook.post == []


async def test_prot18_a_state_sealed_for_another_method_is_rejected(env):
    """PROT-18: a prompts/get state does not let a client retry resources/read."""
    http, app, hook, subs, base_url = env
    status, first = await _read(http, "prompts/get", {"name": "modernup__greeting"})
    status, resp = await _read(
        http,
        "resources/read",
        {
            "uri": "note://secret",
            "inputResponses": {"who": _accept("x")},
            "requestState": first["result"]["requestState"],
        },
        id_=2,
    )
    assert status == 400 and resp["error"]["code"] == INVALID_PARAMS


def test_prot18_a_state_sealed_before_reads_were_bridged_still_unseals():
    """PROT-18: a tool call's state from the previous field set verifies after an upgrade."""
    cipher = TokenCipher([KEY])
    sealed = cipher.encrypt(
        json.dumps(
            {
                "correlation_id": "c",
                "mode": "passthrough",
                "presented_tool": "modernup__ask_name",
                "arguments_digest": arguments_digest({}),
                "sub": "api_key:1",
                "idempotency_key": "k",
                "expires_at": 4102444800.0,
                "upstream_state": "u",
            }
        )
    )
    state = RequestState.unseal(
        cipher,
        sealed,
        method="tools/call",
        target="modernup__ask_name",
        arguments={},
        sub="api_key:1",
    )
    assert state.idempotency_key == "k" and state.method == "tools/call"


async def test_ops7_resumed_call_keeps_key(env):
    """OPS-7: both legs of a paused invocation are audited with the key the hook received."""
    http, app, hook, _subs, _base_url = env
    _status, first = await _call(http, "modernup__ask_name")
    await _call(
        http,
        "modernup__ask_name",
        id_=2,
        inputResponses={"name": _accept("Ada")},
        requestState=first["result"]["requestState"],
    )
    await app.state.container.audit.drain()
    async with app.state.container.session_factory() as db:
        records = (await db.execute(select(AuditRecordRow))).scalars().all()
    [key] = hook.pre
    assert sorted(record.status for record in records) == ["input_required", "success"]
    assert {record.idempotency_key for record in records} == {key}
