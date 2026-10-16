"""Gateway service entrypoint: a thin composition root over the bundlemcp library.

Run: uv run uvicorn --factory apps.gateway.main:app_factory --no-proxy-headers
or:  uv run python apps/gateway/main.py
"""

import asyncio
import socket
from typing import Any

import uvicorn
from bundlemcp.application.serving.replica_drain import ReplicaDrain
from bundlemcp.infrastructure.config.settings import get_settings
from bundlemcp.main.app import create_app


def app_factory():
    return create_app(get_settings())


def server_config() -> uvicorn.Config:
    """How the container serves the app.

    uvicorn's own proxy-header handling is off: it would rewrite the client
    address from X-Forwarded-For for any peer in FORWARDED_ALLOW_IPS before
    the gateway's trusted-proxy policy runs, so the two would disagree. The
    graceful-shutdown timeout is the drain window, so a stop always ends
    within it.
    """
    return uvicorn.Config(
        "main:app_factory",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container entrypoint
        port=8000,
        proxy_headers=False,
        log_config=None,  # the app configures logging for uvicorn's loggers too
        timeout_graceful_shutdown=get_settings().shutdown_drain_seconds,
    )


def drain_of(app: Any) -> ReplicaDrain | None:
    """The drain the composed app published, looking through any wrapping middleware."""
    while app is not None:
        container = getattr(getattr(app, "state", None), "container", None)
        if container is not None:
            return container.drain
        app = getattr(app, "app", None)
    return None


# How long a stopping replica keeps its connections open after it reports not ready, so a load
# balancer's health check sees that and stops routing to it before connections close under it.
UNREADY_GRACE_SECONDS = 2.0


class GatewayServer(uvicorn.Server):
    """uvicorn, starting the replica's drain the moment it is told to stop.

    Draining first reports the replica not ready and refuses new requests with
    a retryable 503, ends the notification streams that would otherwise hold
    the shutdown until its timeout, and cancels the calls still running just
    before it. uvicorn then closes its listener and its idle connections, after
    a short grace in which a load balancer stops sending here.
    """

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        drain = drain_of(self.config.loaded_app)
        if drain is not None:
            drain.begin()
            window = self.config.timeout_graceful_shutdown or 0
            await asyncio.sleep(min(UNREADY_GRACE_SECONDS, window))
        await super().shutdown(sockets)


if __name__ == "__main__":
    GatewayServer(server_config()).run()
