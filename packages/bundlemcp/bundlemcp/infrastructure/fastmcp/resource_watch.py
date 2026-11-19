"""How a pooled session asks its upstream for a resource's updates, by the era it negotiated."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mcp import types as mcp_types
from mcp.client.session import ClientSession

if TYPE_CHECKING:
    from bundlemcp.infrastructure.fastmcp.pooled_session import PooledSession


@runtime_checkable
class ResourceWatch(Protocol):
    """Starts and stops the updates of one resource on one upstream session."""

    async def subscribe(self, session: PooledSession, uri: str) -> None:
        """Ask the upstream for updates of ``uri``, and record it on the session."""
        ...

    async def unsubscribe(self, session: PooledSession, uri: str) -> None:
        """Forget ``uri`` on the session, then stop its updates upstream.

        The URI is dropped first: the subscription may have been made
        through another replica's transport, and must not outlive a failed
        request here.
        """
        ...


class SubscribeResourceWatch:
    """A handshake-era upstream: ``resources/subscribe`` and ``resources/unsubscribe``.

    Sent as explicit protocol requests: the SDK's helpers for them are
    deprecated for every session, although a 2025-era server has no other way
    to send resource updates.
    """

    async def subscribe(self, session: PooledSession, uri: str) -> None:
        await _client_session(session).send_request(
            mcp_types.SubscribeRequest(params=mcp_types.SubscribeRequestParams(uri=uri)),
            mcp_types.EmptyResult,
        )
        session.subscriptions.add(uri)

    async def unsubscribe(self, session: PooledSession, uri: str) -> None:
        session.subscriptions.discard(uri)
        await _client_session(session).send_request(
            mcp_types.UnsubscribeRequest(params=mcp_types.UnsubscribeRequestParams(uri=uri)),
            mcp_types.EmptyResult,
        )


class ListenResourceWatch:
    """A 2026-07-28 upstream: the URI joins or leaves the session's standing listen filter.

    That revision has no subscribe method; the listen stream is re-opened with
    the new filter instead.
    """

    def __init__(self, relisten: Callable[[PooledSession], None]) -> None:
        self._relisten = relisten

    async def subscribe(self, session: PooledSession, uri: str) -> None:
        session.subscriptions.add(uri)
        self._relisten(session)

    async def unsubscribe(self, session: PooledSession, uri: str) -> None:
        session.subscriptions.discard(uri)
        self._relisten(session)


def _client_session(session: PooledSession) -> ClientSession:
    client = session.client
    if client is None:
        raise RuntimeError("a resource is watched only on a session whose transport is open")
    return client.session
