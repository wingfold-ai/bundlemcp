"""AUTH-9 end-to-end OAuth happy path against the compose stack + real Keycloak.

Drives: DCR -> authorize (Keycloak login form + gateway consent) -> code ->
token -> MCP initialize/list/call -> refresh -> introspect, including the IdP
subject (oidc_iss / oidc_sub). The realm's gateway client enforces PKCE S256, so
the gateway's own login to Keycloak (AUTH-15) is exercised with PKCE too. Requires
an oauth-profile endpoint; the demo seed ships an api_key endpoint, so this test
provisions an oauth endpoint via the management API first.
"""

import base64
import hashlib
import re
import secrets
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from helpers import initialize, mcp_call, wait_ready

KEYCLOAK_USER = "admin"
KEYCLOAK_PASSWORD = "admin"
KEYCLOAK_TOKEN_URL = "http://localhost:8080/realms/bundlemcp/protocol/openid-connect/token"
GATEWAY_OIDC_CLIENT_ID = "bundlemcp-gateway"
GATEWAY_OIDC_CLIENT_SECRET = "dev-gateway-secret"
LOGIN_CALLBACK = f"{GATEWAY_URL}/login/callback"


def _send_localhost_secure_cookies(client: httpx.Client) -> None:
    """Send `Secure` cookies back to plain-HTTP localhost, as browsers do.

    Keycloak serves the dev realm as `http://localhost:8080` and, treating
    localhost as a secure context, marks its login-session cookies `Secure`.
    The standard-library cookie jar returns those only over HTTPS, so the login
    form post would arrive without them and Keycloak would answer 400. httpx
    rebuilds the jar for every request, so a cookie policy would not survive;
    clearing the flag as each response is stored does.
    """

    def clear_secure_flag(response: httpx.Response) -> None:
        for cookie in client.cookies.jar:
            if cookie.domain in ("localhost.local", "127.0.0.1"):
                cookie.secure = False

    client.event_hooks["response"].append(clear_secure_flag)


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
            "profile": "oauth_only",
            "auth_modes": ["oauth"],
        },
    ).raise_for_status()


def test_full_oauth_happy_path():
    wait_ready(GATEWAY_URL)
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        _send_localhost_secure_cookies(client)
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
        body = introspect.json()
        assert body["active"] is True
        assert body["aud"] == resource
        # the Keycloak subject travels beside the gateway's own user id.
        # Keycloak's `sub` is the user's id in the realm, a UUID that is not the gateway's.
        assert body["oidc_iss"].endswith("/realms/bundlemcp")
        assert str(uuid.UUID(body["oidc_sub"])) == body["oidc_sub"]
        assert body["oidc_sub"] != body["sub"]


def test_idp_refuses_the_login_code_without_its_verifier():
    """AUTH-15: the gateway's login carries an S256 challenge, so a code taken from its callback
    is useless to anyone without the verifier the gateway kept."""
    wait_ready(GATEWAY_URL)
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        _send_localhost_secure_cookies(client)
        for verifier in ("wrong-" + secrets.token_urlsafe(40), None):
            code = _intercept_login_code(client)
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": LOGIN_CALLBACK,
                "client_id": GATEWAY_OIDC_CLIENT_ID,
                "client_secret": GATEWAY_OIDC_CLIENT_SECRET,
            }
            if verifier is not None:
                data["code_verifier"] = verifier
            replay = client.post(KEYCLOAK_TOKEN_URL, data=data)
            assert replay.status_code == 400, replay.text
            assert replay.json()["error"] == "invalid_grant"


def _intercept_login_code(client: httpx.Client) -> str:
    """Start a gateway login and take Keycloak's code before it reaches the gateway callback."""
    start = client.get(f"{GATEWAY_URL}/login")
    assert start.status_code == 302, start.text
    authorize = httpx.URL(start.headers["location"])
    assert authorize.params["code_challenge_method"] == "S256"
    assert authorize.params["code_challenge"]
    resp = client.get(authorize)
    if resp.status_code == 200:  # no Keycloak session yet: submit the login form
        form_action = re.search(r'action="([^"]+)"', resp.text).group(1).replace("&amp;", "&")
        resp = client.post(
            form_action,
            data={"username": KEYCLOAK_USER, "password": KEYCLOAK_PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    location = resp.headers.get("location", "")
    assert location.startswith(LOGIN_CALLBACK), f"{resp.status_code} {location}"
    return parse_qs(urlparse(location).query)["code"][0]


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
