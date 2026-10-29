"""A server's create defaults and update merge, on the entity (UPS-1, UPS-3, UPS-10, UPS-13)."""

import pytest
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.listing_snapshot_mode import ListingSnapshotMode
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.protocol_mode import NegotiationMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.servers.server_changes import ServerChanges
from pydantic import ValidationError

URL = "https://api.example.com/mcp"
HEADERS = {"Authorization": "Bearer stored"}


def _registered(**fields) -> McpServer:
    return McpServer.register("echo", ServerChanges(url=URL, **fields))


@pytest.mark.parametrize("requested", [ServerAuthMode.NONE, ServerAuthMode.STATIC_HEADERS])
def test_ups1_auth_mode_follows_the_stored_headers(requested):
    """UPS-1: 'none' and 'static_headers' are settled by whether headers are stored, including
    headers kept from before when the write sends none."""
    with_headers = _registered(static_headers=HEADERS, auth_mode=requested)
    assert with_headers.auth_mode == ServerAuthMode.STATIC_HEADERS
    with_headers.reconfigure(ServerChanges(url=URL, auth_mode=requested))
    assert with_headers.auth_mode == ServerAuthMode.STATIC_HEADERS
    assert _registered(auth_mode=requested).auth_mode == ServerAuthMode.NONE


@pytest.mark.parametrize("mode", [ServerAuthMode.UPSTREAM_OAUTH, ServerAuthMode.DELEGATED_TOKEN])
def test_ups1_oauth_and_delegated_modes_are_kept(mode):
    """UPS-1: upstream OAuth and delegated tokens are kept whether or not headers are stored."""
    assert _registered(auth_mode=mode).auth_mode == mode
    assert _registered(auth_mode=mode, static_headers=HEADERS).auth_mode == mode


def test_ups3_empty_static_headers_keep_the_stored_ones():
    """UPS-3: header values are write-only, so a write without headers keeps the stored ones,
    and a write with headers replaces them all."""
    server = _registered(static_headers=HEADERS)
    server.reconfigure(ServerChanges(url=URL))
    assert server.static_headers == HEADERS
    server.reconfigure(ServerChanges(url=URL, static_headers={"X-Key": "new"}))
    assert server.static_headers == {"X-Key": "new"}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://echo:8080/mcp", True),
        ("http://10.0.0.5/mcp", True),
        ("https://api.example.com/mcp", False),
    ],
)
def test_ups13_identity_header_defaults_by_host(url, expected):
    """UPS-13: registered without a choice, the identity header is sent to a server on the
    gateway's own network and not to a public host; an explicit choice wins."""
    assert McpServer.register("s", ServerChanges(url=url)).send_identity_header is expected
    chosen = ServerChanges(url=url, send_identity_header=not expected)
    assert McpServer.register("s", chosen).send_identity_header is (not expected)


def test_ups10_omitted_fields_keep_their_stored_value():
    """UPS-10, UPS-13: a write that leaves the protocol mode, the identity header or the
    listing snapshot out keeps what is stored, while the always-stated fields are replaced."""
    server = _registered(
        description="first",
        send_identity_header=True,
        protocol_mode=NegotiationMode.SESSION,
        listing_snapshot=ListingSnapshotMode.LIVE,
        forward_headers={"x-a": "x-a"},
        identity_mode=IdentityMode.PER_USER,
    )
    server.reconfigure(ServerChanges(url="https://other.example.com/mcp"))
    assert server.protocol_mode == NegotiationMode.SESSION
    assert server.send_identity_header is True
    assert server.listing_snapshot == ListingSnapshotMode.LIVE
    assert server.url == "https://other.example.com/mcp"
    assert server.description is None
    assert server.forward_headers == {}
    assert server.identity_mode == IdentityMode.SHARED


@pytest.mark.parametrize("mode", ["auto", "session", "2026-07-28"])
def test_ups10_named_modes_and_revisions_validate(mode):
    """UPS-10: the named modes and a revision date are valid protocol modes; the named ones
    become the enum."""
    server = McpServer(name="s", url=URL, protocol_mode=mode)
    assert server.protocol_mode == mode
    if mode != "2026-07-28":
        assert isinstance(server.protocol_mode, NegotiationMode)


@pytest.mark.parametrize("mode", ["newest", "legacy", "2026-7-28"])
def test_ups10_unknown_modes_are_rejected_by_the_domain(mode):
    """UPS-10: anything else, the deprecated 'legacy' spelling included, is not a protocol mode
    of the domain; only the API's input accepts that alias."""
    with pytest.raises(ValidationError):
        McpServer(name="s", url=URL, protocol_mode=mode)
