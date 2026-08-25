"""OAS-9 end-to-end OAuth happy path against the compose stack + real Keycloak.

Drives: DCR -> authorize (Keycloak login form + gateway consent) -> code ->
token -> MCP initialize/list/call -> refresh -> introspect. Requires an
oauth-profile endpoint; the demo seed ships an api_key endpoint, so this test
provisions an oauth endpoint via the management API first.
"""

import base64
import hashlib
import re
import secrets
from urllib.parse import parse_qs, urlparse

import httpx
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from tests_integration_helpers import initialize, mcp_call, wait_ready

KEYCLOAK_USER = "admin"
KEYCLOAK_PASSWORD = "admin"


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _ensure_oauth_endpoint(client: httpx.Client) -> None:
    svc = {"Authorization": f"Bearer {SERVICE_KEY}"}
    client.put(
        f"{GATEWAY_URL}/api/v1/endpoints/oauthdemo",
        headers=svc,
        json={
            "name": "oauthdemo",
            "bundle_name": "demo",
            "profile": "claude",
            "auth_modes": ["oauth"],
        },
    ).raise_for_status()


def test_full_oauth_happy_path():
    wait_ready(GATEWAY_URL)
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        _ensure_oauth_endpoint(client)

        # 1. Dynamic client registration
        reg = client.post(
            f"{GATEWAY_URL}/oauth/register",
            json={"redirect_uris": ["http://localhost:8000/callback"], "client_name": "IT"},
        )
        reg.raise_for_status()
        client_id = reg.json()["client_id"]

        # 2. Authorize -> gateway bounces to Keycloak login
        verifier, challenge = _pkce()
        resource = f"{GATEWAY_URL}/oauthdemo/mcp"
        authorize = client.get(
            f"{GATEWAY_URL}/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "http://localhost:8000/callback",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "xyz",
                "resource": resource,
            },
        )
        # follow the chain to Keycloak, submit the login form, come back through
        # consent, and end at the client redirect with ?code=
        code = _drive_login_and_consent(client, authorize)

        # 3. Token exchange
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
        access = token.json()["access_token"]
        refresh = token.json()["refresh_token"]

        # 4. MCP call with the bearer
        session = initialize(GATEWAY_URL, "oauthdemo", bearer=access)
        listing = mcp_call(GATEWAY_URL, "oauthdemo", session, "tools/list", bearer=access)
        assert listing["result"]["tools"]

        # 5. Refresh
        refreshed = client.post(
            f"{GATEWAY_URL}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": client_id,
            },
        )
        refreshed.raise_for_status()
        assert refreshed.json()["access_token"] != access

        # 6. Introspection (service-key gated)
        introspect = client.post(
            f"{GATEWAY_URL}/oauth/introspect",
            data={"token": refreshed.json()["access_token"]},
            headers={"Authorization": f"Bearer {SERVICE_KEY}"},
        )
        introspect.raise_for_status()
        assert introspect.json()["active"] is True
        assert introspect.json()["aud"] == resource


def _follow(client: httpx.Client, resp: httpx.Response) -> httpx.Response:
    while resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers["location"]
        if location.startswith("/"):
            location = GATEWAY_URL + location
        resp = client.get(location)
    return resp


def _drive_login_and_consent(client: httpx.Client, authorize: httpx.Response) -> str:
    # authorize -> /login -> Keycloak authorize -> login form
    page = _follow(client, authorize)
    if "code=" in page.headers.get("location", ""):
        return parse_qs(urlparse(page.headers["location"]).query)["code"][0]

    # submit the Keycloak username/password form
    form_action = re.search(r'action="([^"]+)"', page.text).group(1).replace("&amp;", "&")
    login = client.post(
        form_action,
        data={"username": KEYCLOAK_USER, "password": KEYCLOAK_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    after_login = _follow(client, login)

    # gateway consent page -> approve
    if "Authorize access" in after_login.text:
        token = after_login.text.split('name="token" value="')[1].split('"')[0]
        consent = client.post(
            f"{GATEWAY_URL}/oauth/consent", data={"token": token, "action": "approve"}
        )
        after_login = consent

    # end at the client redirect carrying the code
    location = after_login.headers.get("location", "")
    if location.startswith("http://localhost:8000/callback"):
        return parse_qs(urlparse(location).query)["code"][0]
    raise AssertionError(f"did not reach client redirect; got {after_login.status_code} {location}")
