"""What the bundle advertises: its own prompts and resources, plus its members' discovery
snapshots."""

from typing import Any

from bundlemcp.domain.bundles.bundle_view import BundleView


def aggregate_capabilities(view: BundleView, *, member_notifications: bool) -> dict[str, Any]:
    """Advertise a capability if the bundle itself provides it or an enabled member does.

    A member's source is its discovery-time capabilities snapshot, so initialize
    never fans out to members. The gateway always supports tools. A bundle that
    owns prompts or resources serves them with no member at all.

    A notification is advertised only when the gateway delivers it: the bundle's
    own list changes always, a member's list changes and resource updates only
    when ``member_notifications`` says the gateway relays them to clients.
    """
    caps: dict[str, Any] = {"tools": {"listChanged": True}}
    has_prompts = has_prompts_changes = bool(view.prompts)
    has_resources = has_resources_changes = bool(view.resources)
    has_completions = any(prompt.offers_completions for prompt in view.prompts)
    has_logging = False
    resources_subscribe = False
    for server in view.servers.values():
        member = server.capabilities or {}
        if "prompts" in member:
            has_prompts = True
            if member_notifications and (member.get("prompts") or {}).get("listChanged"):
                has_prompts_changes = True
        if "resources" in member:
            has_resources = True
            resources = member.get("resources") or {}
            if member_notifications and resources.get("listChanged"):
                has_resources_changes = True
            if member_notifications and resources.get("subscribe"):
                resources_subscribe = True
        if "completions" in member:
            has_completions = True
        if "logging" in member:
            has_logging = True
    if has_prompts:
        caps["prompts"] = {"listChanged": True} if has_prompts_changes else {}
    if has_resources:
        advertised: dict[str, Any] = {"listChanged": True} if has_resources_changes else {}
        if resources_subscribe:
            advertised["subscribe"] = True
        caps["resources"] = advertised
    if has_completions:
        caps["completions"] = {}
    if has_logging:
        caps["logging"] = {}
    return caps
