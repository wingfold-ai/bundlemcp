"""The browser pages the gateway renders itself, and what each one is given."""

from enum import StrEnum


class AuthPage(StrEnum):
    """One gateway-rendered page, named by its template file.

    The member's value is the file name an operator's override must use.
    """

    CONSENT = "consent.html"
    RETURN_TO_CLIENT = "return_to_client.html"
    CONNECTED = "connected.html"
    CONNECT_REFUSED = "connect_refused.html"
    ACCOUNT_DEACTIVATED = "account_deactivated.html"

    @property
    def sample_values(self) -> dict[str, str]:
        """Plausible values for every variable this page receives, and no others.

        The keys are the page's template contract: the controllers pass exactly
        these names, and the startup check renders each page with these values.
        """
        return _SAMPLE_VALUES[self]


_SAMPLE_VALUES: dict[AuthPage, dict[str, str]] = {
    AuthPage.CONSENT: {
        "client_name": "Example Client",
        "endpoint_name": "example",
        "bundle_name": "example-bundle",
        "scope": "mcp",
        "token": "sample-consent-token",
        "consent_action": "/oauth/consent",
        "user_email": "person@example.com",
    },
    AuthPage.RETURN_TO_CLIENT: {
        "client_name": "Example Client",
        "heading": "Access granted",
        "location": "https://client.example/callback?code=sample",
    },
    AuthPage.CONNECTED: {"server_name": "example-upstream"},
    AuthPage.CONNECT_REFUSED: {},
    AuthPage.ACCOUNT_DEACTIVATED: {},
}
