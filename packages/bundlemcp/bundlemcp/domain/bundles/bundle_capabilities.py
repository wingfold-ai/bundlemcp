"""What the bundle advertises: its own prompts and resources, plus its members' discovery
snapshots."""

from functools import reduce

from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.servers.server_capabilities import ServerCapabilities


def aggregate_capabilities(view: BundleView, *, member_notifications: bool) -> ServerCapabilities:
    """Advertise a capability if the bundle itself provides it or an enabled member does.

    A member's source is its discovery-time capabilities snapshot, so initialize
    never fans out to members. The gateway always supports tools. A bundle that
    owns prompts or resources serves them with no member at all.

    A notification is advertised only when the gateway delivers it: the bundle's
    own list changes always, a member's list changes and resource updates only
    when ``member_notifications`` says the gateway relays them to clients.
    """
    own = ServerCapabilities.of_bundle_content(
        prompts=bool(view.prompts),
        resources=bool(view.resources),
        completions=any(prompt.offers_completions for prompt in view.prompts),
    )
    members = (
        server.capabilities.relayable(member_notifications) for server in view.servers.values()
    )
    return reduce(ServerCapabilities.union, members, own).with_tools_list_changed()
