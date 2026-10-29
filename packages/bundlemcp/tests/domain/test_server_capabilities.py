"""The capabilities snapshot an upstream advertised, typed where the gateway reads it."""

from typing import Any

import pytest
from bundlemcp.domain.servers.server_capabilities import ServerCapabilities
from bundlemcp.domain.servers.server_capability import ServerCapability

# Every capabilities snapshot the suite stores or probes, plus the edges a probe can write.
SNAPSHOTS: list[dict[str, Any]] = [
    {},
    {"tools": {}},
    {"resources": {}},
    {"tools": {}, "resources": {}},
    {"tools": {}, "prompts": {}},
    {"prompts": {}, "resources": {}, "completions": {}},
    {"prompts": {"listChanged": True}, "resources": {"listChanged": True, "subscribe": True}},
    {"prompts": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False},
     "completions": {}},
    {"tools": {"listChanged": True}, "resources": {"subscribe": True}, "logging": {}},
    {"tools": {"listChanged": True}, "resources": {"subscribe": True}, "logging": {},
     "prompts": {"listChanged": True}},
    {"resources": {"subscribe": False, "listChanged": False}},
    {"resources": {"subscribe": True, "listChanged": True}},
    {
        "experimental": {"acme/streaming": {"chunked": True}},
        "logging": {},
        "prompts": {"listChanged": False},
        "resources": {"subscribe": True, "listChanged": True, "x-extra": 1},
        "tools": {"listChanged": True},
        "completions": {},
        "x-vendor": [1, 2],
    },
]


@pytest.mark.parametrize("snapshot", SNAPSHOTS)
def test_ups22_round_trip_is_identity(snapshot: dict[str, Any]) -> None:
    """UPS-22: a stored snapshot reads and serialises back to the same keys in the same order."""
    capabilities = ServerCapabilities.model_validate(snapshot)

    for dumped in (capabilities.model_dump(), capabilities.model_dump(mode="json")):
        assert dumped == snapshot
        assert list(dumped) == list(snapshot)
        for key, value in snapshot.items():
            if isinstance(value, dict):
                assert list(dumped[key]) == list(value)
    assert ServerCapabilities.model_validate_json(capabilities.model_dump_json()) == capabilities


def test_ups22_presence_is_advertising() -> None:
    """UPS-22: an empty object advertises its capability; an absent key does not."""
    capabilities = ServerCapabilities.model_validate({"prompts": {}, "logging": {}})

    assert capabilities.advertises(ServerCapability.PROMPTS)
    assert capabilities.advertises(ServerCapability.LOGGING)
    assert not capabilities.advertises(ServerCapability.RESOURCES)
    assert not capabilities.advertises(ServerCapability.COMPLETIONS)
    assert not capabilities.prompts_list_changed
    assert not capabilities.accepts_resource_subscriptions


def test_prot11_union_keeps_presence_and_ors_flags() -> None:
    """PROT-11: a union advertises what either side does; a flag is set when either sets it,
    and is left out, not false, when neither does."""
    first = ServerCapabilities.model_validate(
        {"prompts": {"listChanged": False}, "resources": {"subscribe": True}, "x": 1}
    )
    second = ServerCapabilities.model_validate(
        {"resources": {"listChanged": True, "subscribe": False}, "logging": {}}
    )

    union = first.union(second)

    assert union.model_dump() == {
        "prompts": {},
        "resources": {"listChanged": True, "subscribe": True},
        "logging": {},
    }
    assert second.union(first) == union
    assert ServerCapabilities().union(ServerCapabilities()).model_dump() == {}


def test_prot11_relayable_drops_tools_and_unrelayed_flags() -> None:
    """PROT-11: a member never lends the bundle its tools, and lends its list-change and
    subscribe flags only while the gateway relays its notifications."""
    member = ServerCapabilities.model_validate(
        {
            "tools": {"listChanged": True},
            "prompts": {"listChanged": True},
            "resources": {"listChanged": True, "subscribe": True},
            "completions": {},
            "logging": {},
            "experimental": {"a": {}},
        }
    )

    assert member.relayable(False).model_dump() == {
        "prompts": {},
        "resources": {},
        "completions": {},
        "logging": {},
    }
    assert member.relayable(True).model_dump() == {
        "prompts": {"listChanged": True},
        "resources": {"listChanged": True, "subscribe": True},
        "completions": {},
        "logging": {},
    }


def test_prot11_tools_list_changed_is_added_in_front() -> None:
    """PROT-11: the bundle always advertises tools with listChanged, as its first key."""
    own = ServerCapabilities.of_bundle_content(prompts=True, resources=False, completions=True)

    assert list(own.with_tools_list_changed().model_dump().items()) == [
        ("tools", {"listChanged": True}),
        ("prompts", {"listChanged": True}),
        ("completions", {}),
    ]
