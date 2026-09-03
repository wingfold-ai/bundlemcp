from bundlemcp.settings import Settings


def clamp_post_login_redirect(next_url: str, settings: Settings) -> str:
    """Only relative paths or allowlisted web origins survive; anything else goes home."""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    allowed = [settings.public_base] + [o.rstrip("/") for o in settings.web_origins]
    if any(next_url == a or next_url.startswith(a + "/") for a in allowed):
        return next_url
    return "/"
