"""Assembling what one endpoint serves: its bundle's tools, prompts and resources."""

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.bundles.tool_presentation import present_tool


async def load_bundle_view(uow: UnitOfWork, endpoint_name: str) -> BundleView | None:
    """Everything needed to serve one endpoint, or None when it is unknown or disabled."""
    endpoint = await uow.endpoints.by_name(endpoint_name)
    if endpoint is None or not endpoint.enabled:  # EP-5
        return None
    bundle = await uow.bundles.get(endpoint.bundle_id)
    if bundle is None:
        return None

    memberships = await uow.memberships.for_bundle(bundle.id)
    enabled_ids = [m.server_id for m in memberships if m.enabled]  # BND-4
    enabled_servers = {s.name: s for s in await uow.servers.by_ids(enabled_ids)}
    server_by_id = {s.id: s for s in enabled_servers.values()}

    curation = {c.tool_id: c for c in await uow.curations.for_bundle(bundle.id)}
    tools: list[PresentedTool] = []
    for tool in await uow.tools.for_servers(server_by_id):
        presented = present_tool(
            server_by_id[tool.server_id], tool, curation.get(tool.id), endpoint.profile
        )
        if presented is not None:
            tools.append(presented)
    tools.sort(key=lambda t: t.presented_name)
    return BundleView(
        endpoint=endpoint,
        bundle=bundle,
        servers=enabled_servers,
        tools=tools,
        prompts=await uow.bundle_prompts.listings(bundle.id),  # BND-25
        resources=await uow.bundle_resources.listings(bundle.id),
    )
