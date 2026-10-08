"""Which redirect URIs become a CSP form-action source expression (SEC-6)."""

import pytest
from bundlemcp.api.oauth.pages.form_action_source import form_action_source


@pytest.mark.parametrize(
    "redirect_uri, source",
    [
        ("https://claude.ai/api/mcp/auth_callback", "https://claude.ai/api/mcp/auth_callback"),
        ("https://claude.ai/api/mcp/auth_callback?x=1#f", "https://claude.ai/api/mcp/auth_callback"),
        ("https://Client.Example:8443/cb", "https://client.example:8443/cb"),
        ("http://localhost:33418/callback", "http://localhost:33418/callback"),
        ("http://127.0.0.1/cb", "http://127.0.0.1/cb"),
        ("https://client.example", "https://client.example"),
        ("https://client.example/a%2Cb", "https://client.example/a%2Cb"),
    ],
)
def test_expressible_redirect_uri(redirect_uri, source):
    """SEC-6: scheme, host, explicit port and path; never the query or fragment."""
    assert form_action_source(redirect_uri) == source


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "com.example.app:/callback",  # custom scheme of a native app
        "https://user@client.example/cb",  # userinfo
        "https://[::1]/cb",  # IPv6 literal
        "https://*.client.example/cb",  # wildcard host
        "https://client.example/cb;v=1",  # ';' would end the directive
        "https://client.example/a,b",  # ',' would end the policy
        "https://client.example/a b",
        "https://client.example/it's",
        "https://client.example:99999/cb",  # invalid port
        "https:///cb",
    ],
)
def test_unexpressible_redirect_uri(redirect_uri):
    """SEC-6: a URI that cannot be written safely yields no source at all."""
    assert form_action_source(redirect_uri) is None
