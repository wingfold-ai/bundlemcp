"""Smoke + restart-under-load against the compose stack (SES-12)."""

import subprocess

import httpx
import pytest
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from tests_integration_helpers import initialize, mcp_call, wait_ready


def test_readyz():
    wait_ready(GATEWAY_URL)
    resp = httpx.get(f"{GATEWAY_URL}/readyz", timeout=10)
    assert resp.status_code == 200


def test_demo_endpoint_answers_with_api_key():
    """The seeded demo bundle serves tools over the api_key endpoint (BOOT-6/DOC-3)."""
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, "demo", api_key=SERVICE_KEY)
    tools = mcp_call(GATEWAY_URL, "demo", session, "tools/list", api_key=SERVICE_KEY)
    names = {t["name"] for t in tools["result"]["tools"]}
    assert "echo__echo" in names

    result = mcp_call(
        GATEWAY_URL,
        "demo",
        session,
        "tools/call",
        {"name": "echo__echo", "arguments": {"text": "hello"}},
        api_key=SERVICE_KEY,
    )
    assert result["result"]["content"][0]["text"] == "hello"


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="docker CLI required to restart the gateway",
)
def test_session_survives_gateway_restart():
    """SES-12: a session established before a gateway restart keeps working."""
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, "demo", api_key=SERVICE_KEY)

    subprocess.run(
        ["docker", "compose", "-f", "deploy/docker-compose.yml", "restart", "gateway"],
        check=True,
    )
    wait_ready(GATEWAY_URL)

    # same session id, no re-initialize -> must still resolve (no 404 storm)
    tools = mcp_call(GATEWAY_URL, "demo", session, "tools/list", api_key=SERVICE_KEY)
    assert tools["result"]["tools"]  # served from the Redis-backed session record
