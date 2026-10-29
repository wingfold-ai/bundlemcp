"""The login binding cookie's name and attributes."""

from bundlemcp.api.oauth.browser_state.browser_state_ttl import BROWSER_STATE_TTL
from bundlemcp.api.oauth.login_binding_cookie import (
    login_binding_cookie_kwargs,
    login_binding_cookie_name,
)


def test_auth15_binding_cookie_attributes_follow_public_url():
    """AUTH-15: https gets the __Host- name and Secure; both are host-only, HttpOnly, Lax,
    on Path=/ and live as long as the login state."""
    assert login_binding_cookie_name(True) == "__Host-bmcp_login"
    assert login_binding_cookie_name(False) == "bmcp_login"
    for secure in (True, False):
        kwargs = login_binding_cookie_kwargs(secure)
        assert kwargs == {
            "httponly": True,
            "samesite": "lax",
            "secure": secure,
            "max_age": BROWSER_STATE_TTL,
            "path": "/",
        }
        assert "domain" not in kwargs
    assert BROWSER_STATE_TTL == 600
