"""What the bundle advertises, derived from its members' discovery snapshots."""

from typing import Any

from bundlemcp.domain.bundles.bundle_view import BundleView


def aggregate_capabilities(view: BundleView) -> dict[str, Any]:
    """PROT-11: advertise a capability iff ≥1 enabled member advertises it.

    Source is each member's discovery-time capabilities snapshot (DISC-6), so
    initialize never fans out to members. The gateway always supports tools.
    """
    caps: dict[str, Any] = {"tools": {"listChanged": True}}
    has_prompts = has_resources = has_completions = has_logging = False
    resources_subscribe = False
    for server in view.servers.values():
        member = server.capabilities or {}
        if "prompts" in member:
            has_prompts = True
        if "resources" in member:
            has_resources = True
            if (member.get("resources") or {}).get("subscribe"):
                resources_subscribe = True
        if "completions" in member:
            has_completions = True
        if "logging" in member:
            has_logging = True
    if has_prompts:
        caps["prompts"] = {"listChanged": True}
    if has_resources:
        resources: dict[str, Any] = {"listChanged": True}
        if resources_subscribe:
            resources["subscribe"] = True
        caps["resources"] = resources
    if has_completions:
        caps["completions"] = {}
    if has_logging:
        caps["logging"] = {}
    return caps
