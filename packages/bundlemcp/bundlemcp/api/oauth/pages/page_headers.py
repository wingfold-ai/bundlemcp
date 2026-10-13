"""Hardening headers for the browser-facing auth pages."""

# every directive but form-action is the same on every page.
_PAGE_POLICY = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"


def page_headers(*, form_redirect_source: str | None = None) -> dict[str, str]:
    """Headers for an auth page whose forms post to the gateway.

    A browser applies ``form-action`` to the redirect that answers a form post
    too, so a page whose form is answered with a redirect to a client names that
    client's redirect URI here as ``form_redirect_source``; every other page
    leaves it out and stays same-origin.
    """
    form_action = "'self'"
    if form_redirect_source is not None:
        form_action += f" {form_redirect_source}"
    return {
        "Content-Security-Policy": f"{_PAGE_POLICY}; form-action {form_action}",
        "X-Frame-Options": "DENY",
        "Cache-Control": "no-store",
    }


PAGE_HEADERS = page_headers()
