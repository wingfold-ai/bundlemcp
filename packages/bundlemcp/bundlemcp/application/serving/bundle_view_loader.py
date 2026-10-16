"""Assembling what one endpoint serves: its bundle's tools, prompts and resources."""

import uuid

import structlog

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.serving.tool_chain import ToolChain
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.bundles.member_entry_curation import MemberEntryCuration
from bundlemcp.domain.bundles.member_entry_ref import MemberEntryRef
from bundlemcp.domain.bundles.presented_name_claims import PresentedNameClaims
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind

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
    # presentation only: the call stages act per call, on the tools this builds
    chain = ToolChain.for_endpoint(profiles.get(endpoint.profile))
    tools: list[PresentedTool] = []
    for tool in await uow.tools.for_servers(server_by_id):
        presented = chain.present(server_by_id[tool.server_id], tool, curation.get(tool.id))
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
        member_curations=await _member_curations(uow, bundle.id, server_by_id),
        endpoint=endpoint,
        bundle=bundle,
        servers={server.name: server for server in server_by_id.values()},
        tools=sorted(claims.kept, key=lambda t: t.presented_name),
        prompts=await uow.bundle_prompts.listings(bundle.id),
        resources=await uow.bundle_resources.listings(bundle.id),
    )


async def _member_curations(
    uow: UnitOfWork, bundle_id: uuid.UUID, server_by_id: dict[uuid.UUID, McpServer]
) -> dict[MemberEntryRef, MemberEntryCuration]:
    """The bundle's curation of its members' prompts and resources, by live listing identity.

    A bundle without such curation costs one query and loads nothing further.
    """
    curations = {c.entry_id: c for c in await uow.member_curations.for_bundle(bundle_id)}
    if not curations:
        return {}
    curated: dict[MemberEntryRef, MemberEntryCuration] = {}
    for kind in MemberEntryKind:
        for entry in await uow.member_entries.for_servers(server_by_id, kind):
            if entry.id in curations:
                ref = MemberEntryRef(
                    kind=kind, server_name=server_by_id[entry.server_id].name, key=entry.key
                )
                curated[ref] = curations[entry.id]
    return curated
