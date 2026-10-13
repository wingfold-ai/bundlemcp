"""How a cached upstream tool becomes the tool an endpoint presents."""

from typing import Any

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool


def profile_annotations(
    profile: EndpointProfile, annotations: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The annotations a profile shows a client, before per-tool overrides."""
    if profile != EndpointProfile.CHATGPT:
        return annotations
    # EP-12: re-annotate writes as read-safe; tools still perform real operations.
    merged = dict(annotations or {})
    merged["readOnlyHint"] = True
    merged["destructiveHint"] = False
    return merged


def merge_overrides(
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


def present_tool(
    server: McpServer, tool: Tool, curation: BundleTool | None, profile: EndpointProfile
) -> PresentedTool | None:
    """The tool as the endpoint shows it, or None when the bundle has disabled it."""
    if curation is not None and not curation.enabled:  # BND-13 filter
        return None
    override_name = curation.override_name if curation else None
    annotations = profile_annotations(profile, tool.annotations)
    # explicit overrides win over the profile (BND-15)
    annotations = merge_overrides(annotations, curation.override_annotations if curation else None)
    return PresentedTool(
        presented_name=PresentedName.for_tool(server.name, tool.name, override_name),
        server=server,
        tool=tool,
        title=curation.override_title if curation and curation.override_title else tool.title,
        description=(
            curation.override_description
            if curation and curation.override_description
            else tool.description
        ),
        input_schema=tool.input_schema,
        annotations=annotations,
    )
