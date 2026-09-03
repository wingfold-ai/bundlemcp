"""Shared helpers for the compose-driven integration suite."""

import time

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
