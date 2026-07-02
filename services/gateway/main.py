"""Gateway service entrypoint (ARC-6: thin composition root).

Run: uv run uvicorn --factory services.gateway.main:app_factory
or:  uv run python services/gateway/main.py
"""

import logging

import structlog
import uvicorn
from bundlemcp.api.app import create_app
from bundlemcp.settings import get_settings


def _configure_logging(level: str) -> None:
    """OBS-1: structured JSON logs to stdout."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
    )


def app_factory():
    settings = get_settings()
    _configure_logging(settings.log_level)
    return create_app(settings)


if __name__ == "__main__":
    uvicorn.run(
        "main:app_factory",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container entrypoint
        port=8000,
    )
