"""Sign a test user in through the gateway's OAuth server and the dev Keycloak realm.

Drives what an MCP client and its user do: dynamic client registration, the
authorize request with PKCE, the Keycloak login form, the gateway's consent
page, and the token exchange.
"""

import base64
import hashlib
import re
import secrets
from urllib.parse import parse_qs, urlparse

import httpx
from conftest import GATEWAY_URL  # noqa: TID252

KEYCLOAK_USER = "admin"
KEYCLOAK_PASSWORD = "admin"
CLIENT_REDIRECT_URI = "http://localhost:8000/callback"


def send_localhost_secure_cookies(client: httpx.Client) -> None:
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


def pkce() -> tuple[str, str]:
    """A fresh PKCE verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def follow(client: httpx.Client, resp: httpx.Response) -> httpx.Response:
    """Follow redirects by hand, resolving gateway-relative locations."""
    while resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers["location"]
        if location.startswith("/"):
            location = GATEWAY_URL + location
        resp = client.get(location)
    return resp


def drive_login_and_consent(client: httpx.Client, authorize: httpx.Response) -> str:
    """From the gateway's authorize response to the authorization code at the client."""
    # authorize -> /login -> Keycloak authorize -> login form
    page = follow(client, authorize)
    if "code=" in page.headers.get("location", ""):
        return parse_qs(urlparse(page.headers["location"]).query)["code"][0]

    # submit the Keycloak username/password form
    form_action = re.search(r'action="([^"]+)"', page.text).group(1).replace("&amp;", "&")
    login = client.post(
        form_action,
        data={"username": KEYCLOAK_USER, "password": KEYCLOAK_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    after_login = follow(client, login)

    # gateway consent page -> approve
    if "Authorize access" in after_login.text:
        token = after_login.text.split('name="token" value="')[1].split('"')[0]
        consent = client.post(
            f"{GATEWAY_URL}/oauth/consent", data={"token": token, "action": "approve"}
        )
        after_login = consent

    # end at the client redirect carrying the code
    location = after_login.headers.get("location", "")
    if location.startswith(CLIENT_REDIRECT_URI):
        return parse_qs(urlparse(location).query)["code"][0]
    raise AssertionError(f"did not reach client redirect; got {after_login.status_code} {location}")


def oauth_token_for(endpoint: str) -> str:
    """An access token for one endpoint: registration, authorize, consent and token exchange."""
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        send_localhost_secure_cookies(client)
        reg = client.post(
            f"{GATEWAY_URL}/oauth/register",
            json={"redirect_uris": [CLIENT_REDIRECT_URI], "client_name": f"IT-{endpoint}"},
        )
        reg.raise_for_status()
        client_id = reg.json()["client_id"]
        verifier, challenge = pkce()
        authorize = client.get(
            f"{GATEWAY_URL}/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": CLIENT_REDIRECT_URI,
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": endpoint,
                "resource": f"{GATEWAY_URL}/{endpoint}/mcp",
            },
        )
        code = drive_login_and_consent(client, authorize)
        token = client.post(
            f"{GATEWAY_URL}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CLIENT_REDIRECT_URI,
                "code_verifier": verifier,
                "client_id": client_id,
            },
        )
        token.raise_for_status()
        return token.json()["access_token"]
