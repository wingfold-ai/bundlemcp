"""The endpoint resource identifier (AUTH-10, RFC 8707 / RFC 9728)."""

import pytest
from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource

BASE = "https://gw.example.com"


def test_url_and_metadata_url_share_one_shape():
    """AUTH-10: the identifier and its metadata document derive from one object."""
    resource = EndpointResource(public_base=BASE, endpoint_name="ep1")
    assert resource.url == f"{BASE}/ep1/mcp"
    assert resource.metadata_url == f"{BASE}/.well-known/oauth-protected-resource/ep1/mcp"


def test_parse_round_trips_a_built_identifier():
    """AUTH-10: what the gateway advertises is what it accepts back as `resource`."""
    built = EndpointResource(public_base=BASE, endpoint_name="ep1")
    assert EndpointResource.parse(BASE, built.url) == built


@pytest.mark.parametrize(
    "resource",
    [
        "https://other.example.com/ep1/mcp",  # another host
        f"{BASE}/ep1",  # missing the path suffix
        f"{BASE}//mcp",  # empty name
        f"{BASE}/a/b/mcp",  # a path, not a name
        f"{BASE}/.well-known/oauth-protected-resource/ep1/mcp",  # the metadata URL
        "",
    ],
)
def test_parse_rejects_identifiers_that_are_not_an_endpoint(resource):
    """AUTH-10: a `resource` that is not one of ours yields no endpoint name."""
    assert EndpointResource.parse(BASE, resource) is None
