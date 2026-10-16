"""DEP-9 key rotation against the compose stack: prepend a key, sweep, drop the old one."""

import json
import os
import subprocess
import time

import httpx
import pytest
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from cryptography.fernet import Fernet, InvalidToken
from helpers import wait_ready

COMPOSE = ["docker", "compose", "-f", "deploy/docker-compose.yml"]
REPLICAS = [*COMPOSE, "-f", "deploy/docker-compose.replicas.yml"]
DEFAULT_KEY = "Uqw2PEJomK66Xa6lD-TmIU75wHfWRU6T1n9jpYqjv80="  # the compose file's default
SERVER = "rotation-check"
SWEEP_SECONDS = 3


def _replicas() -> tuple[list[str], list[str]]:
    """The compose command and gateway services: both replicas when the overlay is running."""
    running = subprocess.run(
        [*REPLICAS, "ps", "-q", "gateway-b"], capture_output=True, text=True
    ).stdout.strip()
    return (REPLICAS, ["gateway", "gateway-b"]) if running else (COMPOSE, ["gateway"])


def _restart_gateway(keys: list[str] | None, interval: int | None = None) -> None:
    """Recreate every gateway replica with these keys (None: the compose defaults).

    A rotation reaches every replica: one still holding the old list could run
    the sweep and know nothing of the new key.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("BUNDLEMCP_TOKEN_")}
    if keys is not None:
        env["BUNDLEMCP_TOKEN_ENCRYPTION_KEYS"] = json.dumps(keys)
    if interval is not None:
        env["BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL"] = str(interval)
    compose, services = _replicas()
    subprocess.run([*compose, "up", "-d", "--no-deps", "--wait", *services], check=True, env=env)
    wait_ready(GATEWAY_URL)


def _stored_secret() -> str:
    query = (
        "SELECT c.client_secret_encrypted FROM upstream_oauth_clients c "
        f"JOIN mcp_servers s ON s.id = c.server_id WHERE s.name = '{SERVER}'"
    )
    out = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "bundlemcp",
            "-d",
            "bundlemcp",
            "-tAc",
            query,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _wait_until_readable_with(key: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            Fernet(key.encode()).decrypt(_stored_secret().encode())
            return
        except InvalidToken:
            time.sleep(1)
    raise AssertionError("the sweep never moved the secret under the new key")


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="docker CLI required to restart the gateway with other keys",
)
def test_rotated_key_can_be_dropped_after_the_sweep():
    """DEP-9: prepend a key, let the sweep move a stored secret, then run on the new key alone."""
    wait_ready(GATEWAY_URL)
    service = {"Authorization": f"Bearer {SERVICE_KEY}"}
    new_key = Fernet.generate_key().decode()
    with httpx.Client(base_url=GATEWAY_URL, headers=service, timeout=30) as api:
        api.put(
            f"/api/v1/upstreams/{SERVER}",
            json={"name": SERVER, "url": "http://echo-mcp:9000/mcp", "auth_mode": "upstream_oauth"},
        ).raise_for_status()
        api.put(
            f"/api/v1/upstreams/{SERVER}/upstream-oauth",
            json={"client_id": "rotation-client", "client_secret": "s3cret"},
        ).raise_for_status()
    assert Fernet(DEFAULT_KEY.encode()).decrypt(_stored_secret().encode()) == b"s3cret"

    try:
        _restart_gateway([new_key, DEFAULT_KEY], interval=SWEEP_SECONDS)
        _wait_until_readable_with(new_key)

        _restart_gateway([new_key])  # the old key is gone; the gateway still starts and serves
        with httpx.Client(base_url=GATEWAY_URL, headers=service, timeout=30) as api:
            status = api.get(f"/api/v1/upstreams/{SERVER}/upstream-oauth")
            assert status.status_code == 200, status.text
        assert Fernet(new_key.encode()).decrypt(_stored_secret().encode()) == b"s3cret"
    finally:
        # rotate back, so the rest of the suite runs on the compose default again
        _restart_gateway([DEFAULT_KEY, new_key], interval=SWEEP_SECONDS)
        _wait_until_readable_with(DEFAULT_KEY)
        _restart_gateway(None)
        with httpx.Client(base_url=GATEWAY_URL, headers=service, timeout=30) as api:
            api.delete(f"/api/v1/upstreams/{SERVER}")
