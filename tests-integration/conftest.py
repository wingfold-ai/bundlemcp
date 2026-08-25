"""Integration tests run against the live compose stack (spec 30 SES-12, spec 20 OAS-9).

Gated by BUNDLEMCP_INTEGRATION=1 so the default hermetic suite never touches
Docker/network. Run locally with:

    docker compose -f deploy/docker-compose.yml up -d --build
    BUNDLEMCP_INTEGRATION=1 uv run pytest tests-integration -q
"""

import os

import pytest

GATEWAY_URL = os.environ.get("BUNDLEMCP_GATEWAY_URL", "http://localhost:8000")
SERVICE_KEY = os.environ.get(
    "BUNDLEMCP_INITIAL_SERVICE_KEY", "bmcp_sk_devservicekey000000000000000000000000"
)

def pytest_collection_modifyitems(config, items):
    """Skip the whole suite unless the compose stack is opted in (module-wide)."""
    if os.environ.get("BUNDLEMCP_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(
        reason="integration tests require the compose stack (set BUNDLEMCP_INTEGRATION=1)"
    )
    for item in items:
        item.add_marker(skip)
