"""The cookie that ties an admin login to the browser that started it.

`/login` puts a fresh random value in this cookie and parks only its hash with the
login state; the callback finishes the login only when the browser presents the
value again. A callback link handed to another browser therefore signs nobody in.
"""

from bundlemcp.api.oauth.browser_state.browser_state_ttl import BROWSER_STATE_TTL

# The __Host- prefix makes a browser refuse the cookie unless it is Secure, host-only
# and on Path=/, so neither a sibling subdomain nor plain http can plant it. Browsers
# also refuse it on a plain-http deployment, which therefore uses the bare name.
SECURE_LOGIN_BINDING_COOKIE = "__Host-bmcp_login"
LOGIN_BINDING_COOKIE = "bmcp_login"


def login_binding_cookie_name(secure: bool) -> str:
    """The cookie's name: `__Host-`-prefixed exactly when the public URL is https."""
    return SECURE_LOGIN_BINDING_COOKIE if secure else LOGIN_BINDING_COOKIE


def login_binding_cookie_kwargs(secure: bool) -> dict[str, bool | int | str]:
    """httpOnly, SameSite=Lax, host-only on Path=/; Secure iff the public URL is https.

    It lives exactly as long as the login state it is bound to.
    """
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "max_age": BROWSER_STATE_TTL,
        "path": "/",
    }
