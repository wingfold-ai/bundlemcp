"""Two gateway replicas behind a round-robin proxy (SES-12, SES-19, UPS-39, UPS-40, DEP-7).

Needs the replica overlay on top of the core stack:

    docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.replicas.yml \\
        up -d --build --wait
"""

import os
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from helpers import Load, initialize, mcp_call, wait_ready

LB_URL = os.environ.get("BUNDLEMCP_LB_URL", "http://localhost:8100")
B_URL = os.environ.get("BUNDLEMCP_GATEWAY_B_URL", "http://localhost:8002")
COMPOSE = [
    "docker",
    "compose",
    "-f",
    "deploy/docker-compose.yml",
    "-f",
    "deploy/docker-compose.replicas.yml",
]
BUDGET_SECONDS = 2.0
# what a client may see while a replica is replaced: an answer, or "retry"
RETRYABLE = {200, 503}

pytestmark = pytest.mark.replicas


@pytest.fixture(autouse=True, scope="module")
def replicas_running():
    try:
        wait_ready(LB_URL, timeout=10)
        wait_ready(B_URL, timeout=10)
    except TimeoutError:
        pytest.skip("the replica overlay (deploy/docker-compose.replicas.yml) is not running")


def _service() -> httpx.Client:
    return httpx.Client(headers={"Authorization": f"Bearer {SERVICE_KEY}"}, timeout=30)


def _within_budget(check) -> float:
    """Seconds until ``check()`` holds, failing once the propagation budget is spent."""
    started = time.monotonic()
    while True:
        if check():
            return time.monotonic() - started
        if time.monotonic() - started > BUDGET_SECONDS:
            pytest.fail(f"not effective on the other replica within {BUDGET_SECONDS}s")
        time.sleep(0.05)


def _sessions(count: int) -> list[str]:
    return [initialize(LB_URL, "demo", api_key=SERVICE_KEY) for _ in range(count)]


def _all_serve(sessions: list[str]) -> None:
    for session in sessions:
        tools = mcp_call(LB_URL, "demo", session, "tools/list", api_key=SERVICE_KEY)
        assert tools["result"]["tools"]


def test_ses12_two_replica_round_robin():
    """SES-12: ten requests on one session alternate between the replicas and all succeed."""
    session = initialize(LB_URL, "demo", api_key=SERVICE_KEY)
    served_by = set()
    with httpx.Client(timeout=30) as http:
        for turn in range(10):
            resp = http.post(
                f"{LB_URL}/demo/mcp",
                headers={"Mcp-Session-Id": session, "Authorization": f"Bearer {SERVICE_KEY}"},
                json={"jsonrpc": "2.0", "id": turn, "method": "tools/list", "params": {}},
            )
            assert resp.status_code == 200, resp.text
            served_by.add(resp.headers["X-Served-By"])
    assert served_by == {"gateway:8000", "gateway-b:8000"}


def test_ses12_sessions_survive_a_restart_under_load():
    """SES-12: both replicas restart one after the other while clients keep sending requests;
    no request is answered 404 or 500 and every session serves without re-initializing."""
    sessions = _sessions(4)
    with Load(LB_URL, "demo", sessions, SERVICE_KEY) as load:
        for service in ("gateway", "gateway-b"):
            subprocess.run([*COMPOSE, "restart", service], check=True)
            subprocess.run([*COMPOSE, "up", "-d", "--no-deps", "--wait", service], check=True)
        time.sleep(1)
    assert set(load.statuses) <= RETRYABLE, dict(load.statuses)
    assert load.statuses[200] > 0
    _all_serve(sessions)


def test_ses12_an_upstream_restart_costs_no_client_visible_error():
    """SES-12: an upstream restarted between two calls of a session; the second succeeds."""
    session = initialize(LB_URL, "demo", api_key=SERVICE_KEY)
    call = {"name": "echo__echo", "arguments": {"text": "x"}}
    mcp_call(LB_URL, "demo", session, "tools/call", call, api_key=SERVICE_KEY)
    subprocess.run([*COMPOSE, "restart", "echo-mcp"], check=True)
    # restarted since: the upstream is serving again, and has forgotten the session
    deadline = time.monotonic() + 30
    while not _echo_serves():
        assert time.monotonic() < deadline, "echo-mcp did not come back"
        time.sleep(0.2)
    result = mcp_call(LB_URL, "demo", session, "tools/call", call, api_key=SERVICE_KEY)
    assert result["result"]["content"][0]["text"] == "x"


def _echo_serves() -> bool:
    """Whether the demo upstream accepts connections on its published port."""
    try:
        httpx.get("http://127.0.0.1:9100/mcp", timeout=2)
    except httpx.TransportError:
        return False
    return True


def _initialize_status(base_url: str, endpoint: str, key: str) -> int:
    return httpx.post(
        f"{base_url}/{endpoint}/mcp",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
        timeout=30,
    ).status_code


def test_ses19_endpoint_disable_reaches_the_other_replica_within_the_budget():
    """SES-19: an endpoint disabled through replica A answers 404 through B within 2 s."""
    name = f"prop-{uuid.uuid4().hex[:8]}"
    endpoint = {"name": name, "bundle_name": "demo", "auth_modes": ["api_key"]}
    with _service() as admin:
        admin.put(f"{GATEWAY_URL}/api/v1/endpoints/{name}", json=endpoint).raise_for_status()
        try:
            assert _initialize_status(B_URL, name, SERVICE_KEY) == 200
            disabled = {**endpoint, "enabled": False}
            admin.put(f"{GATEWAY_URL}/api/v1/endpoints/{name}", json=disabled).raise_for_status()
            _within_budget(lambda: _initialize_status(B_URL, name, SERVICE_KEY) == 404)
        finally:
            admin.delete(f"{GATEWAY_URL}/api/v1/endpoints/{name}")


def test_ses19_key_deactivation_reaches_the_other_replica_within_the_budget():
    """SES-19: a key deactivated through replica A is refused with 401 through B within 2 s."""
    with _service() as admin:
        created = admin.post(
            f"{GATEWAY_URL}/api/v1/api-keys",
            json={"name": f"prop-{uuid.uuid4().hex[:8]}", "kind": "service"},
        )
        created.raise_for_status()
        key = created.json()
        try:
            assert _initialize_status(B_URL, "demo", key["key"]) == 200
            admin.post(f"{GATEWAY_URL}/api/v1/api-keys/{key['id']}:deactivate").raise_for_status()
            _within_budget(lambda: _initialize_status(B_URL, "demo", key["key"]) == 401)
        finally:
            admin.delete(f"{GATEWAY_URL}/api/v1/api-keys/{key['id']}")


def test_ses19_tool_disable_reaches_the_other_replica_within_the_budget():
    """SES-19: a tool disabled through replica A is gone from tools/list through B within 2 s,
    and a call to it is rejected."""
    with _service() as admin:
        tools = admin.get(f"{GATEWAY_URL}/api/v1/bundles/demo/tools")
        tools.raise_for_status()
        [echo] = [t for t in tools.json() if t["presented_name"] == "echo__echo"]
        url = f"{GATEWAY_URL}/api/v1/bundles/demo/tools/{echo['tool_id']}"
        session = initialize(B_URL, "demo", api_key=SERVICE_KEY)

        def listed() -> set[str]:
            result = mcp_call(B_URL, "demo", session, "tools/list", api_key=SERVICE_KEY)
            return {tool["name"] for tool in result["result"]["tools"]}

        assert "echo__echo" in listed()
        admin.put(url, json={"enabled": False}).raise_for_status()
        try:
            _within_budget(lambda: "echo__echo" not in listed())
            call = {"name": "echo__echo", "arguments": {"text": "x"}}
            result = mcp_call(B_URL, "demo", session, "tools/call", call, api_key=SERVICE_KEY)
            assert "error" in result or result["result"].get("isError")
        finally:
            admin.put(url, json={"enabled": True}).raise_for_status()


ECHO_UPSTREAM_URL = "http://echo-mcp:9000/mcp"


def _tool_names(admin: httpx.Client, name: str) -> list[str]:
    resp = admin.get(f"{GATEWAY_URL}/api/v1/upstreams/{name}/tools", params={"limit": 500})
    resp.raise_for_status()
    return [tool["name"] for tool in resp.json()["items"]]


def test_ups39_a_refresh_right_after_a_save_never_fails():
    """UPS-39: registering an upstream starts a background discovery; a refresh sent at once
    waits for it instead of colliding, answers 200, and every tool is cached once."""
    with _service() as admin:
        for _ in range(8):
            name = f"race-{uuid.uuid4().hex[:8]}"
            try:
                admin.put(
                    f"{GATEWAY_URL}/api/v1/upstreams/{name}",
                    json={"name": name, "url": ECHO_UPSTREAM_URL},
                ).raise_for_status()
                refreshed = admin.post(f"{GATEWAY_URL}/api/v1/upstreams/{name}:refresh-tools")
                assert refreshed.status_code == 200, refreshed.text
                assert refreshed.json()["discovered"] > 0
                names = _tool_names(admin, name)
                assert names and len(names) == len(set(names)), names
            finally:
                admin.delete(f"{GATEWAY_URL}/api/v1/upstreams/{name}")


def test_ups39_refreshes_on_two_replicas_at_once_store_each_tool_once():
    """UPS-39: the same upstream refreshed through both replicas at the same moment: both
    answer 200, and its tools are cached once each."""
    with _service() as admin:
        for _ in range(4):
            name = f"race-{uuid.uuid4().hex[:8]}"
            try:
                admin.put(
                    f"{GATEWAY_URL}/api/v1/upstreams/{name}",
                    json={"name": name, "url": ECHO_UPSTREAM_URL},
                ).raise_for_status()

                def refresh(base: str, upstream: str = name) -> httpx.Response:
                    with _service() as client:
                        return client.post(f"{base}/api/v1/upstreams/{upstream}:refresh-tools")

                with ThreadPoolExecutor(max_workers=2) as pool:
                    answers = list(pool.map(refresh, [GATEWAY_URL, B_URL]))
                assert [a.status_code for a in answers] == [200, 200], [a.text for a in answers]
                names = _tool_names(admin, name)
                assert names and len(names) == len(set(names)), names
            finally:
                admin.delete(f"{GATEWAY_URL}/api/v1/upstreams/{name}")


def test_ups40_an_upstream_deleted_during_a_refresh_stays_deleted():
    """UPS-40: an upstream deleted through one replica while a refresh of it runs on the other
    stays deleted once the refresh has finished: never served again by name, never listed."""
    delays = [0.0, 0.02, 0.05, 0.08, 0.12, 0.16, 0.2, 0.25]
    with _service() as admin:
        for delay in delays:
            name = f"gone-{uuid.uuid4().hex[:8]}"
            admin.put(
                f"{GATEWAY_URL}/api/v1/upstreams/{name}",
                json={"name": name, "url": ECHO_UPSTREAM_URL},
            ).raise_for_status()
            # the background probe the save started is done once the server reports ready
            _within_ready(admin, name)

            def refresh(upstream: str = name) -> httpx.Response:
                with _service() as client:
                    return client.post(f"{GATEWAY_URL}/api/v1/upstreams/{upstream}:refresh-tools")

            with ThreadPoolExecutor(max_workers=1) as pool:
                refreshing = pool.submit(refresh)
                time.sleep(delay)
                deleted = admin.delete(f"{B_URL}/api/v1/upstreams/{name}")
                refreshed = refreshing.result()
            assert deleted.status_code == 204, deleted.text
            assert refreshed.status_code in {200, 404}, refreshed.text
            for base in (GATEWAY_URL, B_URL):
                assert admin.get(f"{base}/api/v1/upstreams/{name}").status_code == 404, delay
                listed = admin.get(f"{base}/api/v1/upstreams", params={"limit": 500}).json()
                assert name not in [item["name"] for item in listed["items"]], delay


def _within_ready(admin: httpx.Client, name: str, timeout: float = 15.0) -> None:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        state = admin.get(f"{GATEWAY_URL}/api/v1/upstreams/{name}").json()["connection_state"]
        if state == "ready":
            return
        time.sleep(0.1)
    pytest.fail(f"{name} was not discovered within {timeout}s")


def _revision(service: str) -> str:
    container = subprocess.run(
        [*COMPOSE, "ps", "-q", service], check=True, capture_output=True, text=True
    ).stdout.strip()
    return subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "org.opencontainers.image.revision"}}',
            container,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_dep7_a_rolling_update_under_load_keeps_every_session():
    """DEP-7: a newly built image replaces the replicas one at a time while clients keep sending
    requests; none is answered 404 or 500 and every session serves afterwards."""
    build = f"rollout-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [*COMPOSE, "build", "--build-arg", f"BUNDLEMCP_BUILD={build}", "gateway", "gateway-b"],
        check=True,
    )
    sessions = _sessions(4)
    with Load(LB_URL, "demo", sessions, SERVICE_KEY) as load:
        for service in ("gateway", "gateway-b"):
            subprocess.run([*COMPOSE, "up", "-d", "--no-deps", "--wait", service], check=True)
        time.sleep(1)
    assert set(load.statuses) <= RETRYABLE, dict(load.statuses)
    assert _revision("gateway") == _revision("gateway-b") == build
    _all_serve(sessions)
