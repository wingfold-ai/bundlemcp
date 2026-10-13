"""Smoke + restart-under-load against the compose stack (SES-12)."""

import subprocess
import time

import httpx
import pytest
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from helpers import initialize, mcp_call, wait_ready


def test_readyz():
    wait_ready(GATEWAY_URL)
    resp = httpx.get(f"{GATEWAY_URL}/readyz", timeout=10)
    assert resp.status_code == 200


def test_demo_endpoint_answers_with_api_key():
    """The seeded demo bundle serves tools over the api_key endpoint (MGMT-13/DOC-3)."""
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


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="docker CLI required to restart Valkey",
)
def test_valkey_restart_costs_one_reinitialize_and_no_500():
    """SES-14 (#85): after a Valkey restart the gateway reconnects on its own.

    The first request after the restart is not a 500: a fresh initialize works,
    and a session from before gets exactly the 404 re-initialize signal.
    """
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, "demo", api_key=SERVICE_KEY)
    assert mcp_call(GATEWAY_URL, "demo", session, "tools/list", api_key=SERVICE_KEY)["result"]

    compose = ["docker", "compose", "-f", "deploy/docker-compose.yml"]
    # Empty the store first, so a snapshot written on shutdown cannot bring the
    # session back and the outcome does not depend on Valkey's persistence.
    subprocess.run([*compose, "exec", "-T", "valkey", "valkey-cli", "FLUSHALL"], check=True)
    subprocess.run([*compose, "restart", "valkey"], check=True)
    subprocess.run([*compose, "up", "-d", "--wait", "valkey"], check=True)

    fresh = initialize(GATEWAY_URL, "demo", api_key=SERVICE_KEY)
    assert fresh

    stale = httpx.post(
        f"{GATEWAY_URL}/demo/mcp",
        headers={"Mcp-Session-Id": session, "Authorization": f"Bearer {SERVICE_KEY}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        timeout=30,
    )
    assert stale.status_code == 404, stale.text

    session = initialize(GATEWAY_URL, "demo", api_key=SERVICE_KEY)
    assert mcp_call(GATEWAY_URL, "demo", session, "tools/list", api_key=SERVICE_KEY)["result"]


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="docker CLI required to stop the IdP and restart the gateway",
)
def test_gateway_started_without_idp_picks_it_up_without_restart():
    """AUTH-21 (#86): login recovers once the IdP is up; nothing else waits on it."""
    compose = ["docker", "compose", "-f", "deploy/docker-compose.yml"]
    subprocess.run([*compose, "stop", "keycloak"], check=True)
    try:
        subprocess.run([*compose, "restart", "gateway"], check=True)
        wait_ready(GATEWAY_URL)  # readiness does not depend on the IdP

        login = httpx.get(f"{GATEWAY_URL}/login", timeout=30)
        assert login.status_code == 503, login.text
        assert int(login.headers["Retry-After"]) > 0

        # An existing credential keeps working on MCP endpoints while the IdP is down.
        session = initialize(GATEWAY_URL, "demo", api_key=SERVICE_KEY)
        assert mcp_call(GATEWAY_URL, "demo", session, "tools/list", api_key=SERVICE_KEY)["result"]
    finally:
        subprocess.run([*compose, "up", "-d", "--wait", "keycloak"], check=True)

    deadline = time.time() + 90
    while True:
        login = httpx.get(f"{GATEWAY_URL}/login", timeout=30)
        if login.status_code == 302 or time.time() > deadline:
            break
        time.sleep(2)
    assert login.status_code == 302, login.text
    assert "/realms/bundlemcp/protocol/openid-connect/auth" in login.headers["location"]
