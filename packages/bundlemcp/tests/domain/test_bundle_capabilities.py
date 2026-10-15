"""What a bundle advertises, and which notifications it may promise (PROT-11)."""

from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_capabilities import aggregate_capabilities
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.bundles.resource_listing import ResourceListing
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.servers.mcp_server import McpServer

MEMBER = McpServer(
    name="docs",
    url="http://docs/mcp",
    capabilities={
        "prompts": {"listChanged": True},
        "resources": {"listChanged": True, "subscribe": True},
    },
)


def _view(*, members: list[McpServer], resources: list[ResourceListing] | None = None):
    bundle = Bundle(name="b")
    return BundleView(
        endpoint=Endpoint(name="e", bundle_id=bundle.id),
        bundle=bundle,
        servers={m.name: m for m in members},
        tools=[],
        resources=resources or [],
    )


def test_prot11_zero_members_advertise_tools_only():
    """PROT-11: a bundle without members or own content offers exactly tools, with listChanged."""
    caps = aggregate_capabilities(_view(members=[]), member_notifications=False)
    assert caps == {"tools": {"listChanged": True}}


def test_prot11_undelivered_member_notifications_are_not_advertised():
    """PROT-11: without delivery of member list changes and resource updates, a member-only
    source of prompts and resources is advertised without listChanged and subscribe."""
    caps = aggregate_capabilities(_view(members=[MEMBER]), member_notifications=False)
    assert caps["prompts"] == {}
    assert caps["resources"] == {}


def test_prot11_delivered_member_notifications_are_advertised():
    """PROT-11: once the gateway relays them, member listChanged and subscribe are advertised."""
    caps = aggregate_capabilities(_view(members=[MEMBER]), member_notifications=True)
    assert caps["prompts"] == {"listChanged": True}
    assert caps["resources"] == {"listChanged": True, "subscribe": True}


def test_prot11_own_resources_keep_list_changed():
    """PROT-11: the bundle's own resources change through the gateway, which announces it."""
    view = _view(members=[MEMBER], resources=[ResourceListing(name="r")])
    caps = aggregate_capabilities(view, member_notifications=False)
    assert caps["resources"] == {"listChanged": True}
