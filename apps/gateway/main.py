"""Gateway service entrypoint: a thin composition root over the bundlemcp library.

Run: uv run uvicorn --factory apps.gateway.main:app_factory --no-proxy-headers
or:  uv run python apps/gateway/main.py
"""

import uvicorn
from bundlemcp.infrastructure.config.settings import get_settings
from bundlemcp.main.app import create_app


def app_factory():
    return create_app(get_settings())


def server_config() -> uvicorn.Config:
    """How the container serves the app.

    uvicorn's own proxy-header handling is off: it would rewrite the client
    address from X-Forwarded-For for any peer in FORWARDED_ALLOW_IPS before
    the gateway's trusted-proxy policy runs, so the two would disagree.
    """
    return uvicorn.Config(
        "main:app_factory",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container entrypoint
        port=8000,
        proxy_headers=False,
        log_config=None,  # the app configures logging for uvicorn's loggers too
    )


if __name__ == "__main__":
    uvicorn.Server(server_config()).run()
