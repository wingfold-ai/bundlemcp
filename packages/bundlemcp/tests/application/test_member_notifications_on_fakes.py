"""A member's notifications between calls, typed and routed to their handlers, on fakes.

PROT-7, PROT-10, PROT-23.
"""

import uuid
from typing import Any

import pytest
from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscription,
)
from bundlemcp.application.contracts.upstream.member_notification import (
    ListedKind,
    MemberListChanged,
    MemberLogMessage,
    MemberResourceUpdated,
)
from bundlemcp.application.schemas.servers.discovery_result import DiscoveryResult
from bundlemcp.application.serving.member_notifications.member_list_change_handler import (
    MemberListChangeHandler,
)
from bundlemcp.application.serving.member_notifications.member_log_message_handler import (
    MemberLogMessageHandler,
)
from bundlemcp.application.serving.member_notifications.member_notification_router import (
    MemberNotificationRouter,
)
from bundlemcp.application.serving.member_notifications.member_resource_update_handler import (
    MemberResourceUpdateHandler,
)
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_server import BundleServer
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.session_record import SessionRecord
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from pydantic import ValidationError

REPORT = "file:///report"


class OnceGate:
    """A shared gate every key passes once, as the gate of several replicas does."""

    def __init__(self) -> None:
        self.held: set[str] = set()

    async def acquire(self, key: str, *, ttl_seconds: int) -> bool:
        if key in self.held:
            return False
        self.held.add(key)
        return True

    async def release(self, key: str) -> None:
        self.held.discard(key)


class Discovery:
    """Records each discovery; ``error`` makes every one fail."""

    def __init__(self, error: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._error = error

    async def discover(self, server_id: uuid.UUID, **options: Any) -> DiscoveryResult:
        self.calls.append(options)
        return DiscoveryResult(error=self._error)


class Subscriptions:
    def __init__(self, by_subscription: dict[ResourceSubscription, list[str]]) -> None:
        self._by_subscription = by_subscription

    async def streams(self, subscription: ResourceSubscription) -> list[str]:
        return self._by_subscription.get(subscription, [])


class Signals:
    def __init__(self) -> None:
        self.delivered: list[tuple[str, dict[str, Any]]] = []

    async def deliver(self, stream_id: str, payload: dict[str, Any]) -> None:
        self.delivered.append((stream_id, payload))


class Sessions:
    def __init__(self, *records: SessionRecord) -> None:
        self._records = {record.session_id: record for record in records}

    async def load(self, session_id: str) -> SessionRecord | None:
        return self._records.get(session_id)


def _record(session_id: str, log_level: str | None) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        endpoint_name="main",
        bundle_name="main",
        identity=CallerIdentity.with_api_key(uuid.uuid4()),
        protocol_version="2025-11-25",
        log_level=log_level,
    )


@pytest.fixture
def server() -> McpServer:
    return McpServer(name="docs", url="https://docs.example/mcp")


def test_prot7_relayed_log_carries_level_logger_and_data_only():
    """PROT-7: the relayed log message is built from the protocol fields alone."""
    message = MemberLogMessage(level="error", logger="db", data={"lost": 3})
    assert message.notification() == {
        "jsonrpc": "2.0",
        "method": "notifications/message",
        "params": {"level": "error", "logger": "db", "data": {"lost": 3}},
    }
    unnamed = MemberLogMessage(level="info", data="hello").notification()
    assert unnamed["params"] == {"level": "info", "data": "hello"}


def test_prot23_relayed_update_carries_the_uri_only():
    """PROT-23: the relayed resource update names the URI and nothing else."""
    assert MemberResourceUpdated(uri=REPORT).notification() == {
        "jsonrpc": "2.0",
        "method": "notifications/resources/updated",
        "params": {"uri": REPORT},
    }


def test_prot23_an_update_without_a_uri_is_not_a_member_notification():
    """PROT-23: an empty URI fails validation instead of reaching a handler."""
    with pytest.raises(ValidationError):
        MemberResourceUpdated(uri="")


def test_prot7_a_level_outside_the_eight_is_not_a_member_notification():
    """PROT-7: a level MCP does not define fails validation."""
    with pytest.raises(ValidationError):
        MemberLogMessage(level="loud", data="x")


async def test_prot10_one_list_change_is_claimed_once(server):
    """PROT-10: two replicas hearing one tool list change cause one discovery."""
    discovery, gate = Discovery(), OnceGate()
    handler = MemberListChangeHandler(InMemoryUnitOfWorkFactory(), discovery, gate)
    change = MemberListChanged(listed=ListedKind.TOOLS)
    await handler.handle(server, change, bound_to=None)
    await handler.handle(server, change, bound_to="s1")
    assert discovery.calls == [{"announce": True}]


async def test_prot10_a_prompt_list_change_relists_prompts(server):
    """PROT-10: a prompt list change re-lists the member's prompts."""
    discovery = Discovery()
    handler = MemberListChangeHandler(InMemoryUnitOfWorkFactory(), discovery, OnceGate())
    await handler.handle(server, MemberListChanged(listed=ListedKind.PROMPTS), bound_to=None)
    assert discovery.calls == [{"relisted": "bundle_prompt"}]


async def test_prot10_failed_rediscovery_still_announces_a_prompt_list_change(server):
    """PROT-10: when re-discovery fails, the member's enabled bundles are still told."""
    uow = InMemoryUnitOfWork()
    bundle = Bundle(name="main")
    uow.servers.add(server)
    uow.bundles.add(bundle)
    uow.memberships.add(BundleServer(bundle_id=bundle.id, server_id=server.id))
    handler = MemberListChangeHandler(
        InMemoryUnitOfWorkFactory(uow),
        Discovery(error="unreachable"),
        OnceGate(),
    )
    await handler.handle(server, MemberListChanged(listed=ListedKind.PROMPTS), bound_to=None)
    assert [(event.entity_type, event.key) for event in uow.published] == [
        ("bundle_prompt", "main")
    ]


async def test_prot23_update_reaches_every_subscribed_stream(server):
    """PROT-23: a resource update is delivered to each stream subscribed to that URI."""
    signals = Signals()
    subscriptions = Subscriptions(
        {ResourceSubscription(server_name="docs", uri=REPORT): ["s1", "listen-7"]}
    )
    handler = MemberResourceUpdateHandler(subscriptions, signals)
    await handler.handle(server, MemberResourceUpdated(uri=REPORT), bound_to=None)
    await handler.handle(server, MemberResourceUpdated(uri="file:///other"), bound_to=None)
    update = MemberResourceUpdated(uri=REPORT).notification()
    assert signals.delivered == [("s1", update), ("listen-7", update)]


async def test_prot7_log_below_the_session_level_is_not_delivered(server):
    """PROT-7: only messages at or above the session's level reach its stream."""
    signals = Signals()
    handler = MemberLogMessageHandler(Sessions(_record("s1", "warning")), signals)
    await handler.handle(server, MemberLogMessage(level="info", data="quiet"), bound_to="s1")
    await handler.handle(server, MemberLogMessage(level="error", data="loud"), bound_to="s1")
    assert [payload["params"]["data"] for _, payload in signals.delivered] == ["loud"]


async def test_prot7_log_without_a_level_set_is_not_delivered(server):
    """PROT-7: a session that never asked for logs receives none."""
    signals = Signals()
    handler = MemberLogMessageHandler(Sessions(_record("s1", None)), signals)
    await handler.handle(server, MemberLogMessage(level="emergency", data="x"), bound_to="s1")
    assert signals.delivered == []


async def test_prot7_log_on_a_shared_session_is_not_delivered(server):
    """PROT-7: a log heard on a session shared between requests belongs to no client."""
    signals = Signals()
    handler = MemberLogMessageHandler(Sessions(_record("s1", "debug")), signals)
    await handler.handle(server, MemberLogMessage(level="error", data="x"), bound_to=None)
    assert signals.delivered == []


async def test_prot23_the_router_sends_each_kind_to_its_handler(server):
    """PROT-23: the router dispatches on the notification's type."""
    heard: list[tuple[str, Any, str | None]] = []

    class Recording:
        def __init__(self, name: str) -> None:
            self.name = name

        async def handle(self, server, notification, *, bound_to):
            heard.append((self.name, notification, bound_to))

    router = MemberNotificationRouter(
        {
            MemberListChanged: Recording("lists"),
            MemberResourceUpdated: Recording("updates"),
            MemberLogMessage: Recording("logs"),
        }
    )
    update = MemberResourceUpdated(uri=REPORT)
    log = MemberLogMessage(level="info", data="x")
    await router.received(server, update, bound_to=None)
    await router.received(server, log, bound_to="s1")
    assert heard == [("updates", update, None), ("logs", log, "s1")]


async def test_prot23_an_unregistered_kind_is_ignored(server):
    """PROT-23: a notification no handler is registered for is dropped, not raised."""
    router = MemberNotificationRouter({})
    await router.received(server, MemberResourceUpdated(uri=REPORT), bound_to=None)
