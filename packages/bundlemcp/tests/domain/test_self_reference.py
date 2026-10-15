"""Recognising this gateway's own MCP endpoints among upstream URLs (BND-5)."""

import pytest
from bundlemcp.domain.servers.self_reference import addresses_gateway_endpoint


@pytest.mark.parametrize(
    ("url", "public", "expected"),
    [
        ("http://localhost:8000/loop-ep/mcp", "http://localhost:8000", True),
        ("https://GW.Example.com/loop-ep/mcp", "https://gw.example.com", True),
        ("https://gw.example.com:443/loop-ep/mcp", "https://gw.example.com", True),
        ("https://gw.example.com/loop-ep/mcp/", "https://gw.example.com/", True),
        ("https://gw.example.com/later/mcp", "https://gw.example.com", True),
        ("https://gw.example.com/gw/loop-ep/mcp", "https://gw.example.com/gw", True),
        ("https://gw.example.com/loop-ep/mcp", "https://gw.example.com/gw", False),
        ("https://gw.example.com/tools/weather/mcp", "https://gw.example.com", False),
        ("https://gw.example.com/loop-ep/mcp/extra", "https://gw.example.com", False),
        ("https://gw.example.com/loop-ep", "https://gw.example.com", False),
        ("https://api.example.com/loop-ep/mcp", "https://gw.example.com", False),
        ("http://gw.example.com/loop-ep/mcp", "https://gw.example.com", False),
        ("https://gw.example.com:8443/loop-ep/mcp", "https://gw.example.com", False),
        ("not a url", "https://gw.example.com", False),
    ],
    ids=[
        "localhost",
        "upper-case-host",
        "explicit-default-port",
        "trailing-slashes",
        "endpoint-not-created-yet",
        "public-path-prefix",
        "missing-public-path-prefix",
        "deeper-path",
        "path-beyond-mcp",
        "not-the-mcp-route",
        "other-host",
        "other-scheme",
        "other-port",
        "garbage",
    ],
)
def test_bnd5_self_reference_is_recognised(url, public, expected):
    """BND-5: any /{name}/mcp under the public URL, in any spelling, is the gateway itself."""
    assert addresses_gateway_endpoint(url, public) is expected
