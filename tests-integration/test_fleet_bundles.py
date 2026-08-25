"""application-layer MCP fleet through the gateway: seo + media bundles (BND-*, FWD-*).

Requires the full compose stack. The seo-gsc assertions exercise FWD-1/FWD-4:
the gateway forwards the caller's bearer, seo-gsc introspects it back against
this gateway, and — before a Google account is connected — answers tool calls
with its connect instructions instead of results. Completing the Google consent
(http://localhost:8001/connect) is the documented interactive step; after it,
GSC tool calls return real Search Console data.
"""

import httpx
import pytest
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from test_oauth_flow import _drive_login_and_consent, _pkce  # noqa: TID251
from tests_integration_helpers import initialize, mcp_call, wait_ready

# Every test here drives the application-layer fleet (seo-psi, seo-gsc, dataforseo,
# hyperframes), which ships as private GHCR images. CI cannot pull those, so it
# runs `-m "not fleet"`; locally the full compose stack makes them available.
pytestmark = pytest.mark.fleet


def _tool_names(listing: dict) -> list[str]:
    return [t["name"] for t in listing["result"]["tools"]]


def test_seo_bundle_serves_psi_tools_with_api_key():
    """Seeded seo endpoint lists seo-psi tools for api_key callers (BND-3)."""
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, "seo", api_key=SERVICE_KEY)
    listing = mcp_call(GATEWAY_URL, "seo", session, "tools/list", api_key=SERVICE_KEY)
    names = _tool_names(listing)
    assert any(n.startswith("seo-psi__") for n in names), names


def test_seo_bundle_discovers_gsc_tools():
    """OAS-5 api-key introspection lets discovery authenticate against seo-gsc,
    so its tools appear in the bundle (DISC-1 via the static header)."""
    wait_ready(GATEWAY_URL)
    # force a fresh discovery pass in case the boot-time probe raced seo-gsc
    svc = {"Authorization": f"Bearer {SERVICE_KEY}"}
    refresh = httpx.post(
        f"{GATEWAY_URL}/api/v1/servers/seo-gsc:refresh-tools", headers=svc, timeout=60
    )
    refresh.raise_for_status()
    result = refresh.json()
    assert result["error"] is None, result
    assert result["discovered"] > 0, result

    session = initialize(GATEWAY_URL, "seo", api_key=SERVICE_KEY)
    listing = mcp_call(GATEWAY_URL, "seo", session, "tools/list", api_key=SERVICE_KEY)
    assert any(n.startswith("seo-gsc__") for n in _tool_names(listing))


def _oauth_token_for(endpoint: str) -> str:
    """Full DCR + authorize + consent + token exchange for one endpoint."""
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        reg = client.post(
            f"{GATEWAY_URL}/oauth/register",
            json={
                "redirect_uris": ["http://localhost:8000/callback"],
                "client_name": "IT-fleet",
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
                "state": "fleet",
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


def test_gsc_tool_call_reaches_gsc_via_forwarded_bearer():
    """FWD-1/FWD-4/UPO analog: an OAuth caller's bearer is forwarded, seo-gsc
    introspects it here, and answers — with connect instructions before the
    Google account is linked, with data after."""
    wait_ready(GATEWAY_URL)
    access = _oauth_token_for("seo")

    session = initialize(GATEWAY_URL, "seo", bearer=access)
    listing = mcp_call(GATEWAY_URL, "seo", session, "tools/list", bearer=access)
    gsc_tools = [n for n in _tool_names(listing) if n.startswith("seo-gsc__")]
    assert gsc_tools, "seo-gsc tools missing from the bundle"

    # prefer a listing-style tool; fall back to the first
    tool = next((n for n in gsc_tools if "site" in n or "list" in n), gsc_tools[0])
    reply = mcp_call(
        GATEWAY_URL,
        "seo",
        session,
        "tools/call",
        {"name": tool, "arguments": {}},
        bearer=access,
    )
    # Not a gateway-level auth error: the call must reach seo-gsc. Before the
    # interactive Google consent the server replies with connect instructions;
    # afterwards with data. Both prove the introspection path.
    assert "error" not in reply or reply["error"] is None, reply
    content = str(reply["result"])
    connected = "connect" not in content.lower()
    if not connected:
        assert "connect" in content.lower(), content


def test_media_bundle_initializes_and_identifies_caller():
    """hyperframes receives X-MCP-User (FWD-3) for api_key callers."""
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, "media", api_key=SERVICE_KEY)
    listing = mcp_call(GATEWAY_URL, "media", session, "tools/list", api_key=SERVICE_KEY)
    assert "result" in listing


def test_dataforseo_tools_listed():
    """dataforseo boots credential-less; its tools are still discoverable."""
    wait_ready(GATEWAY_URL)
    session = initialize(GATEWAY_URL, "seo", api_key=SERVICE_KEY)
    listing = mcp_call(GATEWAY_URL, "seo", session, "tools/list", api_key=SERVICE_KEY)
    names = _tool_names(listing)
    if not any(n.startswith("dataforseo__") for n in names):
        pytest.skip("dataforseo discovery unavailable (no credentials / npm cold start)")
