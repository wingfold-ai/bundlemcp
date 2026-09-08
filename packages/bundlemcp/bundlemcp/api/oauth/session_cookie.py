"""The cookie that carries an admin session id to the browser."""

SESSION_COOKIE = "bmcp_session"


def session_cookie_kwargs(*, secure: bool, max_age: int) -> dict[str, bool | int | str]:
    """httpOnly, SameSite=Lax; Secure iff the public URL is https."""
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "max_age": max_age,
        "path": "/",
    }
