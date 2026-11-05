"""What reaches an upstream that verifies callers itself (UPS-17, AUTH-5, AUTH-27..31).

The seeded `introspect-demo` upstream introspects the bearer it receives against
this gateway and refuses any request whose bearer is not active. Its `whoami`
tool reports the subject the gateway vouched for, the X-MCP-User header, the
mapped tenant header and the names of every header that arrived, so each test
can check the gateway's side of the exchange from the upstream's point of view.
"""

import json

import httpx
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from helpers import initialize, wait_ready
from test_oauth_flow import (  # noqa: TID251
    _drive_login_and_consent,
    _pkce,
    _send_localhost_secure_cookies,
)

ENDPOINT = "passthrough"
UPSTREAM = "introspect-demo"
WHOAMI = f"{UPSTREAM}__whoami"


def _oauth_token_for(endpoint: str) -> str:
    """Full DCR + authorize + consent + token exchange for one endpoint."""
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        _send_localhost_secure_cookies(client)
        reg = client.post(
            f"{GATEWAY_URL}/oauth/register",
            json={
                "redirect_uris": ["http://localhost:8000/callback"],
                "client_name": "IT-passthrough",
            },
        )
        reg.raise_for_status()
        client_id = reg.json()["client_id"]
        verifier, challenge = _pkce()
        authorize = client.get(
            f"{GATEWAY_URL}/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "http://localhost:8000/callback",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "passthrough",
                "resource": f"{GATEWAY_URL}/{endpoint}/mcp",
            },
        )
        code = _drive_login_and_consent(client, authorize)
        token = client.post(
            f"{GATEWAY_URL}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:8000/callback",
                "code_verifier": verifier,
                "client_id": client_id,
            },
        )
        token.raise_for_status()
        return token.json()["access_token"]


def _whoami(token: str, session: str, extra_headers: dict[str, str] | None = None) -> dict:
    """Call the upstream's whoami tool through the gateway and return its report."""
    resp = httpx.post(
        f"{GATEWAY_URL}/{ENDPOINT}/mcp",
        headers={
            "Authorization": f"Bearer {token}",
            "Mcp-Session-Id": session,
            **(extra_headers or {}),
        },
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": WHOAMI, "arguments": {}},
        },
        timeout=30,
    )
    resp.raise_for_status()
    reply = resp.json()
    assert reply.get("error") is None, reply
    result = reply["result"]
    assert not result.get("isError"), result
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def _refresh_upstream() -> dict:
    refresh = httpx.post(
        f"{GATEWAY_URL}/api/v1/upstreams/{UPSTREAM}:refresh-tools",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
        timeout=60,
    )
    refresh.raise_for_status()
    return refresh.json()


def test_ups17_discovery_authenticates_with_the_static_header():
    """UPS-17, AUTH-5: discovery has no caller, so the static authorization header carries
    the service key, which the upstream's introspection accepts as an api_key caller."""
    wait_ready(GATEWAY_URL)
    result = _refresh_upstream()
    assert result["error"] is None, result
    assert result["discovered"] > 0, result


def test_auth30_forwarded_bearer_is_introspected_as_the_user():
    """AUTH-27, AUTH-30: a signed-in caller's bearer is forwarded, and introspecting it at
    the gateway names that user."""
    wait_ready(GATEWAY_URL)
    access = _oauth_token_for(ENDPOINT)
    session = initialize(GATEWAY_URL, ENDPOINT, bearer=access)
    report = _whoami(access, session)
    assert report["signed_in_user"] is True, report
    assert report["sub"], report
    assert not report["sub"].startswith("api_key:"), report
    assert report["identity_header"] == report["sub"], report


def test_auth5_api_key_caller_is_introspected_as_an_api_key():
    """AUTH-5: a forwarded API key is reported active with the `api_key:<id>` subject."""
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, ENDPOINT, api_key=SERVICE_KEY)
    report = _whoami(SERVICE_KEY, session)
    assert report["sub"].startswith("api_key:"), report
    assert report["token_use"] == "api_key", report
    assert report["signed_in_user"] is False, report


def test_auth29_identity_header_is_injected_and_a_spoofed_one_replaced():
    """AUTH-29: the upstream receives X-MCP-User naming the resolved caller, never the value
    the client sent."""
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, ENDPOINT, api_key=SERVICE_KEY)
    report = _whoami(SERVICE_KEY, session, {"X-MCP-User": "spoofed"})
    assert report["identity_header"] == report["sub"], report
    assert report["identity_header"].startswith("api_key:"), report


def test_auth27_mapped_header_is_forwarded_and_an_unlisted_one_is_not():
    """AUTH-27: a header the server maps arrives under its upstream name; a header it does
    not list never reaches it."""
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, ENDPOINT, api_key=SERVICE_KEY)
    report = _whoami(
        SERVICE_KEY, session, {"X-Tenant-Id": "tenant-42", "X-Unlisted": "must-not-arrive"}
    )
    assert report["tenant"] == "tenant-42", report
    assert "x-tenant-id" not in report["header_names"], report
    assert "x-unlisted" not in report["header_names"], report


def test_auth31_forwarded_headers_never_cross_callers():
    """AUTH-31: two callers taking turns on one server each reach it with their own bearer."""
    wait_ready(GATEWAY_URL)
    access = _oauth_token_for(ENDPOINT)
    user_session = initialize(GATEWAY_URL, ENDPOINT, bearer=access)
    key_session = initialize(GATEWAY_URL, ENDPOINT, api_key=SERVICE_KEY)
    for _ in range(3):
        user = _whoami(access, user_session)
        key = _whoami(SERVICE_KEY, key_session)
        assert not user["sub"].startswith("api_key:"), user
        assert key["sub"].startswith("api_key:"), key
