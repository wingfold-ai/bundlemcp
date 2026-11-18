"""What a change of a server's URL moves away from (UPS-41, UPS-42)."""

import pytest
from bundlemcp.domain.servers.url_change import UrlChange
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_client_metadata import UpstreamClientMetadata
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata

OLD = "https://seo.example/mcp"


@pytest.mark.parametrize(
    ("current", "resource", "origin"),
    [
        ("HTTPS://SEO.example/mcp/", False, False),
        ("https://seo.example:443/mcp", True, False),
        ("https://seo.example/v2/mcp", True, False),
        ("https://seo.example:8443/mcp", True, True),
        ("http://seo.example/mcp", True, True),
        ("https://attacker.example/mcp", True, True),
    ],
)
def test_ups41_ups42_a_url_change_names_what_it_moves(current, resource, origin):
    """UPS-41, UPS-42: case and a trailing slash move nothing; a path, or spelling out the
    default port, moves only the resource; scheme, host or port move the origin too."""
    move = UrlChange(previous=OLD, current=current)
    assert move.moves_resource is resource
    assert move.moves_origin is origin


def test_ups41_a_client_record_forgets_its_server_and_keeps_how_it_was_obtained():
    """UPS-41: endpoints and step-up scopes go; identification, grant and unknown keys stay."""
    meta = UpstreamClientMetadata.obtained(
        UpstreamMetadata(authorization_endpoint="https://idp/a", token_endpoint="https://idp/t"),
        ClientIdentification.PREREGISTERED,
    ).configured_by_admin(UpstreamGrant.CLIENT_CREDENTIALS, None, None)
    meta = UpstreamClientMetadata.model_validate(
        {**meta.with_step_up(["admin"]).model_dump(), "vendor_note": "kept"}
    )

    forgotten = meta.forgetting_server()

    assert forgotten.endpoints is None and forgotten.remembered_endpoints is None
    assert forgotten.step_up_scopes == ()
    assert forgotten.is_admin_stored
    assert forgotten.grant == UpstreamGrant.CLIENT_CREDENTIALS
    assert forgotten.model_dump() == {
        "identification": "preregistered",
        "grant_type": "client_credentials",
        "vendor_note": "kept",
    }
