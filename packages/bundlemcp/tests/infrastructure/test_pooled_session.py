"""The lifecycle of one pooled upstream session (SES-8, SES-9)."""

import pytest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.upstream_session_key import UpstreamSessionKey
from bundlemcp.infrastructure.fastmcp.lease_slot import LeaseSlot
from bundlemcp.infrastructure.fastmcp.pooled_session import (
    IllegalSessionTransition,
    PooledSession,
    SessionState,
)
from fastmcp import Client, FastMCP

LEASED, IDLE, RETIRING, CLOSED = (
    SessionState.LEASED,
    SessionState.IDLE,
    SessionState.RETIRING,
    SessionState.CLOSED,
)

# state before -> event -> state after; None where the event is illegal
TRANSITIONS: dict[SessionState, dict[str, SessionState | None]] = {
    LEASED: {"checkout": None, "release": IDLE, "retire": RETIRING, "close": CLOSED},
    IDLE: {"checkout": LEASED, "release": None, "retire": RETIRING, "close": CLOSED},
    RETIRING: {"checkout": None, "release": RETIRING, "retire": RETIRING, "close": CLOSED},
    CLOSED: {"checkout": None, "release": CLOSED, "retire": CLOSED, "close": CLOSED},
}


def _session(state: SessionState = LEASED, **fields) -> PooledSession:
    server = McpServer(name="echo", url="http://upstream.test/mcp", send_identity_header=False)
    key = UpstreamSessionKey.for_request(server, sub="alice", forwarded_headers={}, endpoint="main")
    return PooledSession(
        server=server,
        key=key,
        relay=frozenset(),
        variant=None,
        slot=LeaseSlot(),
        state=state,
        **{"bound_to": None, **fields},
    )


CELLS = [
    (before, event, after) for before, row in TRANSITIONS.items() for event, after in row.items()
]


@pytest.mark.parametrize(("before", "event", "after"), CELLS)
def test_ses8_ses9_every_transition_of_the_table(before, event, after):
    """SES-8/SES-9: each state answers each event as the lifecycle table says."""
    session = _session(before)
    if after is None:
        with pytest.raises(IllegalSessionTransition):
            getattr(session, event)()
        assert session.state is before
    else:
        getattr(session, event)()
        assert session.state is after


def test_ses8_a_new_session_belongs_to_the_lease_that_opened_it():
    """SES-8: a session is created leased, without a transport."""
    session = _session(PooledSession.model_fields["state"].default)
    assert session.state is LEASED
    assert not session.is_open
    assert not session.evictable


def test_ses9_open_means_a_transport_that_was_not_closed_since():
    """SES-9: a session is open from its connect until it is closed."""
    client = Client(FastMCP("echo"))
    assert _session(LEASED, client=client).is_open
    assert _session(RETIRING, client=client).is_open
    assert not _session(CLOSED, client=client).is_open
    assert not _session(IDLE).is_open


def test_ses8_only_an_idle_session_without_subscriptions_is_evictable():
    """SES-8: a leased, retiring, closed or subscribed session is never evicted."""
    assert _session(IDLE).evictable
    assert not _session(IDLE, subscriptions={"file:///a"}).evictable
    assert [state for state in SessionState if _session(state).evictable] == [IDLE]


def test_ses8_only_a_shared_session_is_ended_upstream_on_eviction():
    """SES-8: an evicted bound session keeps its upstream session for its binding."""
    assert _session().ends_upstream_on_eviction
    assert not _session(bound_to="s1").ends_upstream_on_eviction
