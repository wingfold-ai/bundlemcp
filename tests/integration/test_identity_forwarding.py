"""What an upstream learns about its caller, through the identity demo (DEP-17).

The compose stack runs examples/identity-demo-mcp behind the `identity` endpoint
(oauth + api_key). It refuses requests without a credential, introspects the
bearer the gateway forwards against this gateway, and its `whoami` tool reports
the introspected caller and the identity headers it received.
"""

import json

import httpx
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from helpers import initialize, mcp_call, wait_ready
from oauth_login import oauth_token_for

ENDPOINT = "identity"
WHOAMI = "identity-demo__whoami"


def _whoami(session: str, *, extra_headers: dict[str, str] | None = None, **credential) -> dict:
    reply = mcp_call(
        GATEWAY_URL,
        ENDPOINT,
        session,
        "tools/call",
        {"name": WHOAMI, "arguments": {}},
        extra_headers=extra_headers,
        **credential,
    )
    assert reply.get("error") is None, reply
    result = reply["result"]
    assert not result.get("isError"), result
    if "structuredContent" in result:
        return result["structuredContent"]
    return json.loads(result["content"][0]["text"])


def _api_key_session() -> str:
    wait_ready(GATEWAY_URL)
    return initialize(GATEWAY_URL, ENDPOINT, api_key=SERVICE_KEY)


def test_discovery_authenticates_with_the_static_header():
    """UPS-17, AUTH-5: a forced discovery reaches the demo, which refuses requests without a
    credential, through the static header and finds its tool."""
    wait_ready(GATEWAY_URL)
    refresh = httpx.post(
        f"{GATEWAY_URL}/api/v1/upstreams/identity-demo:refresh-tools",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
        timeout=60,
    )
    refresh.raise_for_status()
    result = refresh.json()
    assert result["error"] is None, result
    assert result["discovered"] > 0, result


def test_forwarded_bearer_is_introspected_to_the_signed_in_user():
    """AUTH-30, AUTH-5: an OAuth caller's bearer is forwarded, the demo introspects it here, and
    it names the user: the same subject the identity header carries, with the IdP subject."""
    wait_ready(GATEWAY_URL)
    access = oauth_token_for(ENDPOINT)
    session = initialize(GATEWAY_URL, ENDPOINT, bearer=access)
    seen = _whoami(session, bearer=access)
    assert seen["caller"], seen
    assert not seen["caller"].startswith("api_key:"), seen
    assert seen["caller"] == seen["x_mcp_user"], seen
    assert seen["has_oidc_subject"] is True, seen


def test_api_key_caller_introspects_as_api_key():
    """AUTH-5: a forwarded API key introspects as `api_key:<id>`, the caller the identity header
    names, without an IdP subject."""
    seen = _whoami(_api_key_session(), api_key=SERVICE_KEY)
    assert seen["caller"].startswith("api_key:"), seen
    assert seen["caller"] == seen["x_mcp_user"], seen
    assert seen["has_oidc_subject"] is False, seen


def test_spoofed_identity_header_is_replaced():
    """AUTH-29: a caller's own `X-MCP-User` never reaches the upstream; the gateway's does."""
    seen = _whoami(_api_key_session(), api_key=SERVICE_KEY, extra_headers={"X-MCP-User": "spoofed"})
    assert seen["x_mcp_user"] != "spoofed", seen
    assert seen["x_mcp_user"].startswith("api_key:"), seen


def test_only_mapped_headers_are_forwarded():
    """AUTH-27: a mapped header arrives under its upstream name; an unmapped one does not."""
    seen = _whoami(
        _api_key_session(),
        api_key=SERVICE_KEY,
        extra_headers={"X-Tenant-Id": "tenant-42", "X-Unlisted": "1"},
    )
    assert seen["tenant"] == "tenant-42", seen
    assert "x-tenant-id" not in seen["header_names"], seen
    assert "x-unlisted" not in seen["header_names"], seen


def test_forwarded_identity_never_crosses_callers():
    """AUTH-31: an OAuth caller and an API-key caller, calling alternately on one gateway, each
    see only their own identity."""
    wait_ready(GATEWAY_URL)
    access = oauth_token_for(ENDPOINT)
    user_session = initialize(GATEWAY_URL, ENDPOINT, bearer=access)
    key_session = initialize(GATEWAY_URL, ENDPOINT, api_key=SERVICE_KEY)
    user = _whoami(user_session, bearer=access)["caller"]
    key = _whoami(key_session, api_key=SERVICE_KEY)["caller"]
    assert user != key
    for _ in range(3):
        assert _whoami(user_session, bearer=access)["caller"] == user
        assert _whoami(key_session, api_key=SERVICE_KEY)["caller"] == key
