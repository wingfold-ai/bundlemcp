"""Shared helpers for the compose-driven integration suite."""

import threading
import time
from collections import Counter

import httpx


def wait_ready(base_url: str, timeout: float = 120.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{base_url}/readyz", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(3)
    raise TimeoutError(f"{base_url} not ready within {timeout}s")


def _headers(session: str | None, api_key: str | None, bearer: str | None) -> dict:
    headers = {}
    if session:
        headers["Mcp-Session-Id"] = session
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


def initialize(base_url: str, endpoint: str, *, api_key=None, bearer=None) -> str:
    resp = httpx.post(
        f"{base_url}/{endpoint}/mcp",
        headers=_headers(None, api_key, bearer),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.headers["mcp-session-id"]


def mcp_call(
    base_url, endpoint, session, method, params=None, *, api_key=None, bearer=None
) -> dict:
    resp = httpx.post(
        f"{base_url}/{endpoint}/mcp",
        headers=_headers(session, api_key, bearer),
        json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


class Load:
    """Keeps requests flowing on several sessions in a thread and counts every answer.

    Each request is a ``tools/list`` on one of the sessions, round the list.
    A connection that fails outright is counted as status 0.
    """

    def __init__(self, base_url: str, endpoint: str, sessions: list[str], api_key: str) -> None:
        self._base_url = base_url
        self._endpoint = endpoint
        self._sessions = sessions
        self._api_key = api_key
        self.statuses: Counter[int] = Counter()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> "Load":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=60)

    def _run(self) -> None:
        with httpx.Client(timeout=30) as http:
            turn = 0
            while not self._stop.is_set():
                session = self._sessions[turn % len(self._sessions)]
                turn += 1
                try:
                    resp = http.post(
                        f"{self._base_url}/{self._endpoint}/mcp",
                        headers=_headers(session, self._api_key, None),
                        json={"jsonrpc": "2.0", "id": turn, "method": "tools/list", "params": {}},
                    )
                    self.statuses[resp.status_code] += 1
                except httpx.HTTPError:
                    self.statuses[0] += 1
                time.sleep(0.05)
