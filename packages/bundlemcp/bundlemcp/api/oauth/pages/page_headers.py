"""Hardening headers for the browser-facing auth pages."""

# every directive but form-action is the same on every page.
_PAGE_POLICY = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
# the same, plus the gateway's own origin for an operator's stylesheets, fonts and images.
_PAGE_POLICY_WITH_ASSETS = (
    "default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; "
    "frame-ancestors 'none'"
)


def page_headers(
    *, form_redirect_source: str | None = None, assets: bool = False
) -> dict[str, str]:
    """Headers for an auth page whose forms post to the gateway.

    A browser applies ``form-action`` to the redirect that answers a form post
    too, so a page whose form is answered with a redirect to a client names that
    client's redirect URI here as ``form_redirect_source``; every other page
    leaves it out and stays same-origin. ``assets`` is true while the operator
    serves page assets from the gateway, and admits stylesheets, fonts and
    images from its own origin; nothing else is loosened.
    """
    form_action = "'self'"
    if form_redirect_source is not None:
        form_action += f" {form_redirect_source}"
    policy = _PAGE_POLICY_WITH_ASSETS if assets else _PAGE_POLICY
    return {
        "Content-Security-Policy": f"{policy}; form-action {form_action}",
        "X-Frame-Options": "DENY",
        "Cache-Control": "no-store",
    }
