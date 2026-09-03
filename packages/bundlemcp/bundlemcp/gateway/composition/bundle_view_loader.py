"""Assembling a bundle's presented tool surface for one endpoint."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.gateway.composition.bundle_view import BundleView
from bundlemcp.gateway.composition.presented_tool import PREFIX_SEP, PresentedTool
from bundlemcp.models import (
    Bundle,
    BundleServer,
    BundleTool,
    Endpoint,
    EndpointProfile,
    McpServer,
    Tool,
)


def _apply_profile_annotations(
    profile: str, annotations: dict[str, Any] | None
) -> dict[str, Any] | None:
    if profile != EndpointProfile.CHATGPT:
        return annotations
    # PROF-3: re-annotate writes as read-safe; tools still perform real operations.
    merged = dict(annotations or {})
    merged["readOnlyHint"] = True
    merged["destructiveHint"] = False
    return merged


def _merge_overrides(
    base: dict[str, Any] | None, override: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Shallow merge; explicit per-tool overrides win; a None value removes a key."""
    if override is None:
        return base
    merged = dict(base or {})
    for key, value in override.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged or None


async def load_bundle_view(db: AsyncSession, endpoint_name: str) -> BundleView | None:
    endpoint = (
        await db.execute(select(Endpoint).where(Endpoint.name == endpoint_name))
    ).scalar_one_or_none()
    if endpoint is None or not endpoint.enabled:  # EP-5
        return None
    bundle = (await db.execute(select(Bundle).where(Bundle.id == endpoint.bundle_id))).scalar_one()

    members = (
        (
            await db.execute(
                select(McpServer, BundleServer)
                .join(BundleServer, BundleServer.server_id == McpServer.id)
                .where(BundleServer.bundle_id == bundle.id)
            )
        )
        .tuples()
        .all()
    )
    enabled_servers = {srv.name: srv for srv, mapping in members if mapping.enabled}  # BND-4
    server_by_id = {srv.id: srv for srv in enabled_servers.values()}

    curation = {
        bt.tool_id: bt
        for bt in (
            await db.execute(select(BundleTool).where(BundleTool.bundle_id == bundle.id))
        ).scalars()
    }

    tools: list[PresentedTool] = []
    if server_by_id:
        rows = (
            await db.execute(select(Tool).where(Tool.server_id.in_(server_by_id)))  # type: ignore[attr-defined]
        ).scalars()
        for tool in rows:
            cur = curation.get(tool.id)
            if cur is not None and not cur.enabled:  # TM-2 filter
                continue
            server = server_by_id[tool.server_id]
            presented = (
                cur.override_name
                if cur is not None and cur.override_name
                else f"{server.name}{PREFIX_SEP}{tool.name}"
            )
            annotations = _apply_profile_annotations(endpoint.profile, tool.annotations)
            annotations = _merge_overrides(
                annotations, cur.override_annotations if cur else None
            )  # explicit overrides win over profile (TM-4)
            tools.append(
                PresentedTool(
                    presented_name=presented,
                    server=server,
                    tool=tool,
                    title=(cur.override_title if cur and cur.override_title else tool.title),
                    description=(
                        cur.override_description
                        if cur and cur.override_description
                        else tool.description
                    ),
                    input_schema=tool.input_schema,
                    annotations=annotations,
                )
            )
    tools.sort(key=lambda t: t.presented_name)
    return BundleView(endpoint=endpoint, bundle=bundle, servers=enabled_servers, tools=tools)
