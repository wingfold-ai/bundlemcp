"""What the bundle advertises: its own prompts and resources, plus its members' discovery
snapshots."""

from typing import Any

from bundlemcp.domain.bundles.bundle_view import BundleView


def aggregate_capabilities(view: BundleView) -> dict[str, Any]:
    # PROT-11 (aggregation rule), UPS-22 (the snapshot it reads)
    """Advertise a capability if the bundle itself provides it or an enabled member does.

    A member's source is its discovery-time capabilities snapshot, so initialize
    never fans out to members. The gateway always supports tools. A bundle that
    owns prompts or resources serves them with no member at all.
    """
    # BND-27
    caps: dict[str, Any] = {"tools": {"listChanged": True}}
    has_prompts = bool(view.prompts)
    has_resources = bool(view.resources)
    has_completions = any(prompt.offers_completions for prompt in view.prompts)
    has_logging = False
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
