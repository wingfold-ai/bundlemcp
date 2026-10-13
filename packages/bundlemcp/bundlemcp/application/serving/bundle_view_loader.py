"""Assembling what one endpoint serves: its bundle's tools, prompts and resources."""

import structlog

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.bundles.presented_name_claims import PresentedNameClaims
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.bundles.tool_pipeline import ToolPipeline
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog

log = structlog.get_logger(__name__)


async def load_bundle_view(
    uow: UnitOfWork, endpoint_name: str, profiles: ProfileCatalog
) -> BundleView | None:
    """Everything needed to serve one endpoint, or None when it is unknown or disabled."""
    endpoint = await uow.endpoints.by_name(endpoint_name)
    if endpoint is None or not endpoint.enabled:
        return None
    bundle = await uow.bundles.get(endpoint.bundle_id)
    if bundle is None:
        return None

    memberships = await uow.memberships.for_bundle(bundle.id)
    enabled_ids = [m.server_id for m in memberships if m.enabled]
    fetched = {s.id: s for s in await uow.servers.by_ids(enabled_ids)}
    # in member order, which decides who answers first in a fan-out
    server_by_id = {sid: fetched[sid] for sid in enabled_ids if sid in fetched}

    curation = {c.tool_id: c for c in await uow.curations.for_bundle(bundle.id)}
    pipeline = ToolPipeline.for_profile(profiles.get(endpoint.profile))
    tools: list[PresentedTool] = []
    for tool in await uow.tools.for_servers(server_by_id):
        presented = pipeline.present(server_by_id[tool.server_id], tool, curation.get(tool.id))
        if presented is not None:
            tools.append(presented)
    claims = PresentedNameClaims.settle(tools, curation)
    for displaced in claims.displaced:
        log.warning(
            "bundle.presented_name_collision",
            bundle=bundle.name,
            name=displaced.presented_name,
            displaced=f"{displaced.server.name}/{displaced.tool.name}",
        )
    return BundleView(
        endpoint=endpoint,
        bundle=bundle,
        servers={server.name: server for server in server_by_id.values()},
        tools=sorted(claims.kept, key=lambda t: t.presented_name),
        prompts=await uow.bundle_prompts.listings(bundle.id),
        resources=await uow.bundle_resources.listings(bundle.id),
    )
