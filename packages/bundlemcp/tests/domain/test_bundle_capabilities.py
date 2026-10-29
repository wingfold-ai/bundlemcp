"""What a bundle advertises, and which notifications it may promise (PROT-11)."""

from typing import Any

import pytest
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_capabilities import aggregate_capabilities
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.bundles.prompt_argument import PromptArgument
from bundlemcp.domain.bundles.prompt_listing import PromptListing
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
    caps = aggregate_capabilities(_view(members=[]), member_notifications=False).model_dump()
    assert caps == {"tools": {"listChanged": True}}


def test_prot11_undelivered_member_notifications_are_not_advertised():
    """PROT-11: without delivery of member list changes and resource updates, a member-only
    source of prompts and resources is advertised without listChanged and subscribe."""
    caps = aggregate_capabilities(_view(members=[MEMBER]), member_notifications=False).model_dump()
    assert caps["prompts"] == {}
    assert caps["resources"] == {}


def test_prot11_delivered_member_notifications_are_advertised():
    """PROT-11: once the gateway relays them, member listChanged and subscribe are advertised."""
    caps = aggregate_capabilities(_view(members=[MEMBER]), member_notifications=True).model_dump()
    assert caps["prompts"] == {"listChanged": True}
    assert caps["resources"] == {"listChanged": True, "subscribe": True}


def test_prot11_own_resources_keep_list_changed():
    """PROT-11: the bundle's own resources change through the gateway, which announces it."""
    view = _view(members=[MEMBER], resources=[ResourceListing(name="r")])
    caps = aggregate_capabilities(view, member_notifications=False).model_dump()
    assert caps["resources"] == {"listChanged": True}


WIRE_ORDER = ("tools", "prompts", "resources", "completions", "logging")
TOOLS = {"tools": {"listChanged": True}}
PLAIN = {"prompts": {}, "completions": {}, "experimental": {"x": {}}}
FLAGGED = {
    "tools": {"listChanged": True},
    "prompts": {"listChanged": True},
    "resources": {"subscribe": True},
    "logging": {},
}
FALSE_FLAGS = {"prompts": {"listChanged": False}, "resources": {"listChanged": False}}
SUBSCRIBE_ONLY = {"resources": {"subscribe": True, "listChanged": False}}
OWN_PROMPT = PromptListing(name="p")
COMPLETABLE = PromptListing(name="c", arguments=[PromptArgument(name="k", values=["a"])])


def _member(name: str, capabilities: dict[str, Any]) -> McpServer:
    return McpServer(name=name, url=f"http://{name}/mcp", capabilities=capabilities)


def _advertised(view: BundleView, *, notifications: bool) -> dict[str, Any]:
    """The capabilities object the bundle puts on the wire."""
    return aggregate_capabilities(view, member_notifications=notifications).model_dump()


@pytest.mark.parametrize(
    ("members", "prompts", "resources", "notifications", "wire"),
    [
        ([], [], [], True, TOOLS),
        ([{}], [], [], True, TOOLS),
        ([PLAIN], [], [], False, {**TOOLS, "prompts": {}, "completions": {}}),
        ([PLAIN], [], [], True, {**TOOLS, "prompts": {}, "completions": {}}),
        (
            [FLAGGED],
            [],
            [],
            True,
            {**TOOLS, "prompts": {"listChanged": True}, "resources": {"subscribe": True},
             "logging": {}},
        ),
        ([FLAGGED], [], [], False, {**TOOLS, "prompts": {}, "resources": {}, "logging": {}}),
        (
            [PLAIN, FLAGGED],
            [],
            [],
            True,
            {**TOOLS, "prompts": {"listChanged": True}, "resources": {"subscribe": True},
             "completions": {}, "logging": {}},
        ),
        ([FALSE_FLAGS], [], [], True, {**TOOLS, "prompts": {}, "resources": {}}),
        (
            [FLAGGED],
            [OWN_PROMPT],
            [],
            False,
            {**TOOLS, "prompts": {"listChanged": True}, "resources": {}, "logging": {}},
        ),
        (
            [SUBSCRIBE_ONLY],
            [],
            [ResourceListing(name="r")],
            True,
            {**TOOLS, "resources": {"listChanged": True, "subscribe": True}},
        ),
        (
            [SUBSCRIBE_ONLY],
            [],
            [ResourceListing(name="r")],
            False,
            {**TOOLS, "resources": {"listChanged": True}},
        ),
        (
            [],
            [COMPLETABLE],
            [],
            False,
            {**TOOLS, "prompts": {"listChanged": True}, "completions": {}},
        ),
    ],
)
def test_prot11_aggregation_matrix(members, prompts, resources, notifications, wire):
    """PROT-11: own content and every member's snapshot fold into exactly this wire object;
    a member's list-change and subscribe flags pass only while notifications are relayed,
    tools always change, and keys the gateway does not serve (experimental) are not passed on."""
    bundle = Bundle(name="b")
    view = BundleView(
        endpoint=Endpoint(name="e", bundle_id=bundle.id),
        bundle=bundle,
        servers={f"m{n}": _member(f"m{n}", caps) for n, caps in enumerate(members)},
        tools=[],
        prompts=prompts,
        resources=resources,
    )

    advertised = _advertised(view, notifications=notifications)

    assert advertised == wire
    assert list(advertised) == [key for key in WIRE_ORDER if key in wire]
