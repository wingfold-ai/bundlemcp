"""The ``httpx`` client every gateway-initiated fetch to a configured or remote URL uses."""

from typing import Any

import httpx

from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.egress.egress_scope import EgressScope
from bundlemcp.infrastructure.egress.guarded_backend import guard_pool


def guarded_client(
    settings: Settings, *, scope: EgressScope = EgressScope.UPSTREAM, **options: Any
) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` whose every connection passes the egress policy.

    ``trust_env`` is off: an ``HTTP_PROXY`` in the environment would make the
    dialled address the proxy's and so route around the policy.
    """
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    guard_pool(transport._pool, settings, scope=scope)
    return httpx.AsyncClient(transport=transport, trust_env=False, **options)
