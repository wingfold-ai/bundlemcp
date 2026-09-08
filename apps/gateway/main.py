"""Gateway service entrypoint: a thin composition root over the bundlemcp library.

Run: uv run uvicorn --factory apps.gateway.main:app_factory
or:  uv run python apps/gateway/main.py
"""

import uvicorn
from bundlemcp.infrastructure.config.settings import get_settings
from bundlemcp.main.app import create_app


def app_factory():
    return create_app(get_settings())


if __name__ == "__main__":
    uvicorn.run(
        "main:app_factory",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container entrypoint
        port=8000,
        log_config=None,  # the app configures logging for uvicorn's loggers too
    )
