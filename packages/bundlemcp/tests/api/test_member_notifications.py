"""What members say between calls reaches clients (PROT-7, PROT-10, PROT-17, PROT-23).

The gateway and the upstream both run on loopback uvicorn: notifications
travel on real event streams, which the in-process ASGI transport buffers.
"""

import asyncio
import contextlib
import contextvars
import json
from typing import Any

import pytest
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.listing_snapshot_mode import ListingSnapshotMode
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import display_prefix, hash_token
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.member_listing_row import MemberListingRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides
from fastmcp import Context, FastMCP
from httpx import AsyncClient
from mcp import types
from mcp.shared.subscriptions import SUBSCRIPTION_ID_META_KEY
from mcp.types import (
    CLIENT_CAPABILITIES_META_KEY,
    CLIENT_INFO_META_KEY,
    PROTOCOL_VERSION_META_KEY,
)
from sqlmodel import select

from tests.conftest import ENDPOINT_KEY, hermetic_settings
from tests.loopback_upstream import RecordingUpstream, serving_app, serving_upstream

REPORT = "file:///report"
CAPABILITIES = {
    "tools": {"listChanged": True},
    "resources": {"subscribe": True},
    "logging": {},
}


class Upstream:
    """A member that remembers each session it served, to speak on it later."""

    def __init__(self) -> None:
        self.sessions: list[Any] = []
        self.server = FastMCP("echo")

        @self.server.tool
        def say(text: str, ctx: Context) -> str:
            self._remember(ctx.session)
            return f"said:{text}"

        @self.server.resource(REPORT)
        def report() -> str:
            return "the report"

        async def subscribe(ctx, params: types.SubscribeRequestParams) -> types.EmptyResult:
            self._remember(ctx.session)
            return types.EmptyResult()

        async def unsubscribe(ctx, params: types.UnsubscribeRequestParams) -> types.EmptyResult:
            return types.EmptyResult()

        low_level = self.server._mcp_server
        low_level.add_request_handler(
            "resources/subscribe", types.SubscribeRequestParams, subscribe
        )
        low_level.add_request_handler(
            "resources/unsubscribe", types.UnsubscribeRequestParams, unsubscribe
        )
        self.recording = RecordingUpstream(self.server)

    def _remember(self, session: Any) -> None:
        if session not in self.sessions:
            self.sessions.append(session)

    async def announce(self, notification: types.ServerNotification) -> None:
        """Send ``notification`` on every remembered session's own stream, outside any request."""

        async def send() -> None:
            for session in self.sessions:
                await session.send_notification(notification)

        # in a context of its own, as the upstream's own task would: the test's
        # context would otherwise travel into the upstream with the message
        await asyncio.create_task(send(), context=contextvars.Context())


async def _seed(engine, url: str) -> None:
    async with session_factory(engine)() as db:
        db.add(
            ApiKeyRow(
                name="k",
                key_hash=hash_token(ENDPOINT_KEY),
                key_prefix=display_prefix(ENDPOINT_KEY),
                kind=ApiKeyKind.ENDPOINT,
            )
        )
        server = McpServerRow(
            name="echo", url=url, protocol_mode="legacy", capabilities=CAPABILITIES
        )
        bundle = BundleRow(name="main")
        db.add_all([server, bundle])
        await db.commit()
        await db.refresh(server)
        await db.refresh(bundle)
        db.add(BundleServerRow(bundle_id=bundle.id, server_id=server.id))
        db.add(EndpointRow(name="main", bundle_id=bundle.id, auth_modes=["api_key"]))
        db.add(ToolRow(server_id=server.id, name="say", schema_hash="h", input_schema={}))
        await db.commit()


@contextlib.asynccontextmanager
async def _gateway(engine, redis):
    settings = hermetic_settings(
        egress_allow_cidrs=["127.0.0.1/32"],
        discovery_refresh_interval=0,
        upstream_pooling_enabled=True,
    )
    app = create_app(settings, overrides=CompositionOverrides(engine=engine, redis=redis))
    async with serving_app(app) as base_url:
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http:
            yield http


@pytest.fixture
async def upstream(engine):
    member = Upstream()
    async with serving_upstream(member.recording) as url:
        await _seed(engine, url)
        yield member


async def _initialize(http) -> str:
    resp = await http.post(
        "/main/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.headers["mcp-session-id"]


async def _rpc(http, session_id: str, method: str, params: dict, id_: int = 2) -> dict:
    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _say(http, session_id: str, id_: int = 2) -> dict:
    return await _rpc(
        http, session_id, "tools/call", {"name": "echo__say", "arguments": {"text": "a"}}, id_
    )


class Stream:
    """A client event stream read in the background."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.opened = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def wait_for(self, method: str, timeout: float = 5.0) -> dict:
        async def first() -> dict:
            while True:
                for event in self.events:
                    if event.get("method") == method:
                        return event
                await asyncio.sleep(0.02)

        return await asyncio.wait_for(first(), timeout)

    def start(self, http, method: str, **kwargs) -> None:
        async def read() -> None:
            async with http.stream(method, "/main/mcp", **kwargs) as resp:
                assert resp.status_code == 200
                self.opened.set()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        self.events.append(json.loads(line[6:]))

        self._task = asyncio.create_task(read())

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task


async def _get_stream(http, session_id: str) -> Stream:
    stream = Stream()
    stream.start(http, "GET", headers={"Mcp-Session-Id": session_id})
    await asyncio.wait_for(stream.opened.wait(), 5)
    await asyncio.sleep(0.2)  # the stream is registered once its response has started
    return stream


async def _until(predicate, timeout: float = 5.0) -> None:
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return
        await asyncio.sleep(0.05)
    assert predicate()


async def test_prot10_a_tool_list_change_between_calls_rediscovers_once(engine, redis, upstream):
    """PROT-10: two replicas hear one change; discovery runs once and the GET stream is told."""
    async with _gateway(engine, redis) as a, _gateway(engine, redis) as b:
        session_a, session_b = await _initialize(a), await _initialize(b)
        await _say(a, session_a)
        await _say(b, session_b)
        stream = await _get_stream(a, session_a)
        listed = len(upstream.recording.calls("tools/list"))
        await upstream.announce(types.ToolListChangedNotification())
        event = await stream.wait_for("notifications/tools/list_changed")
        await asyncio.sleep(0.3)
        await stream.close()
    assert event["method"] == "notifications/tools/list_changed"
    assert len(upstream.sessions) == 2
    assert len(upstream.recording.calls("tools/list")) == listed + 1


async def test_prot7_set_level_reaches_members_that_log(engine, redis, upstream):
    """PROT-7: setLevel goes to the member on the session's bound upstream session."""
    async with _gateway(engine, redis) as http:
        session_id = await _initialize(http)
        await _say(http, session_id)
        bound = upstream.recording.calls("tools/call")[-1].session_id
        await _rpc(http, session_id, "logging/setLevel", {"level": "warning"}, 3)
    set_level = upstream.recording.calls("logging/setLevel")
    assert [call.session_id for call in set_level] == [bound]


async def test_prot7_a_log_message_between_calls_reaches_the_get_stream(engine, redis, upstream):
    """PROT-7: a member's log message outside any call arrives on the client's GET stream."""
    async with _gateway(engine, redis) as http:
        session_id = await _initialize(http)
        await _rpc(http, session_id, "logging/setLevel", {"level": "info"}, 3)
        await _say(http, session_id)
        stream = await _get_stream(http, session_id)
        await upstream.announce(
            types.LoggingMessageNotification(
                params=types.LoggingMessageNotificationParams(level="error", data="disk full")
            )
        )
        event = await stream.wait_for("notifications/message")
        await stream.close()
    assert event["params"]["data"] == "disk full"


async def test_prot23_a_resource_update_between_calls_reaches_the_get_stream(
    engine, redis, upstream
):
    """PROT-23: subscribe is relayed on the bound session; its update reaches the GET stream."""
    async with _gateway(engine, redis) as http:
        session_id = await _initialize(http)
        await _rpc(http, session_id, "resources/subscribe", {"uri": REPORT}, 3)
        assert len(upstream.recording.calls("resources/subscribe")) == 1
        stream = await _get_stream(http, session_id)
        await upstream.announce(
            types.ResourceUpdatedNotification(
                params=types.ResourceUpdatedNotificationParams(uri=REPORT)
            )
        )
        event = await stream.wait_for("notifications/resources/updated")
        await stream.close()
    assert event["params"]["uri"] == REPORT


async def test_prot23_unsubscribe_stops_updates_upstream(engine, redis, upstream):
    """PROT-23: resources/unsubscribe is relayed to the member that held the subscription."""
    async with _gateway(engine, redis) as http:
        session_id = await _initialize(http)
        await _rpc(http, session_id, "resources/subscribe", {"uri": REPORT}, 3)
        await _rpc(http, session_id, "resources/unsubscribe", {"uri": REPORT}, 4)
    subscribed = upstream.recording.calls("resources/subscribe")
    unsubscribed = upstream.recording.calls("resources/unsubscribe")
    assert [call.session_id for call in unsubscribed] == [subscribed[0].session_id]


async def test_prot23_a_subscription_survives_an_upstream_session_loss(engine, redis, upstream):
    """PROT-23: after a 404 rebinds the session, the subscription is renewed on the new one."""
    async with _gateway(engine, redis) as http:
        session_id = await _initialize(http)
        await _rpc(http, session_id, "resources/subscribe", {"uri": REPORT}, 3)
        upstream.recording.forget()
        result = await _say(http, session_id, 4)
    assert result["result"]["content"][0]["text"] == "said:a"
    subscribes = upstream.recording.calls("resources/subscribe")
    assert len(subscribes) == 2
    assert subscribes[1].session_id != subscribes[0].session_id


def _listen(notifications: dict) -> tuple[dict, dict]:
    meta = {
        PROTOCOL_VERSION_META_KEY: "2026-07-28",
        CLIENT_CAPABILITIES_META_KEY: {},
        CLIENT_INFO_META_KEY: {"name": "test-client", "version": "1"},
    }
    body = {
        "jsonrpc": "2.0",
        "id": "sub-1",
        "method": "subscriptions/listen",
        "params": {"notifications": notifications, "_meta": meta},
    }
    headers = {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "subscriptions/listen"}
    return body, headers


async def test_prot10_a_member_prompt_list_change_reaches_a_modern_listener(
    engine, redis, upstream
):
    """PROT-10, PROT-17: a member's prompt list change is relayed on the listen stream."""
    body, headers = _listen({"promptsListChanged": True})
    async with _gateway(engine, redis) as http:
        await _say(http, await _initialize(http))  # some session to the member is held
        stream = Stream()
        stream.start(http, "POST", json=body, headers=headers)
        await stream.wait_for("notifications/subscriptions/acknowledged")
        await upstream.announce(types.PromptListChangedNotification())
        changed = await stream.wait_for("notifications/prompts/list_changed")
        await stream.close()
    assert changed["params"]["_meta"][SUBSCRIPTION_ID_META_KEY] == "sub-1"


async def test_prot17_listen_relays_updates_of_subscribed_resources(engine, redis, upstream):
    """PROT-17: resourceSubscriptions are acknowledged, relayed, and ended with the stream."""
    body, headers = _listen({"resourceSubscriptions": [REPORT]})
    async with _gateway(engine, redis) as http:
        stream = Stream()
        stream.start(http, "POST", json=body, headers=headers)
        ack = await stream.wait_for("notifications/subscriptions/acknowledged")
        await upstream.announce(
            types.ResourceUpdatedNotification(
                params=types.ResourceUpdatedNotificationParams(uri=REPORT)
            )
        )
        update = await stream.wait_for("notifications/resources/updated")
        await stream.close()
        await _until(lambda: upstream.recording.calls("resources/unsubscribe"))
    assert ack["params"]["notifications"]["resourceSubscriptions"] == [REPORT]
    assert update["params"]["uri"] == REPORT
    assert update["params"]["_meta"][SUBSCRIPTION_ID_META_KEY] == "sub-1"


async def test_prot10_prompt_list_change_refreshes_snapshot(engine, redis, upstream):
    """PROT-10, BND-8: a member's prompt list change re-lists it before clients are told, so the
    next prompts/list is served the new listing without asking the member again."""

    @upstream.server.prompt(name="greet")
    def greet() -> str:
        return "hello"

    async with session_factory(engine)() as db:
        server = (await db.execute(select(McpServerRow))).scalar_one()
        server.listing_snapshot = ListingSnapshotMode.SHARED
        server.capabilities = {**CAPABILITIES, "prompts": {"listChanged": True}}
        db.add(server)
        db.add(
            MemberListingRow(
                server_id=server.id,
                kind=ListingKind.PROMPTS,
                entries=[{"name": "greet"}],
                listing_hash="seeded",
                listed_at=utcnow(),
            )
        )
        await db.commit()

    async with _gateway(engine, redis) as http:
        session = await _initialize(http)
        await _say(http, session)  # some session to the member is held
        listed = await _rpc(http, session, "prompts/list", {})
        assert [p["name"] for p in listed["result"]["prompts"]] == ["echo__greet"]
        assert upstream.recording.calls("prompts/list") == []

        @upstream.server.prompt(name="farewell")
        def farewell() -> str:
            return "bye"

        stream = await _get_stream(http, session)
        await upstream.announce(types.PromptListChangedNotification())
        await stream.wait_for("notifications/prompts/list_changed")
        await stream.close()
        relisted = len(upstream.recording.calls("prompts/list"))
        listed = await _rpc(http, session, "prompts/list", {}, id_=3)
    assert [p["name"] for p in listed["result"]["prompts"]] == ["echo__greet", "echo__farewell"]
    assert relisted >= 1
    assert len(upstream.recording.calls("prompts/list")) == relisted
