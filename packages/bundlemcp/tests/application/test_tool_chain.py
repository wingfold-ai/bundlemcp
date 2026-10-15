"""The tool chain: filters, profile, overrides, then the call stages (EP-12, EP-13, BND-13/14/15,
PROT-25)."""

import uuid

from bundlemcp.application.serving.presentation_stage import PresentationStage
from bundlemcp.application.serving.tool_chain import ToolChain
from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.curation_filter import CurationFilter
from bundlemcp.domain.bundles.override_stage import OverrideStage
from bundlemcp.domain.bundles.profile_stage import ProfileStage
from bundlemcp.domain.bundles.stale_tool_filter import StaleToolFilter
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.profiles import ProfileCatalog
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool

SERVER = McpServer(name="fs", url="http://fs/mcp")
TOOL = Tool(
    server_id=SERVER.id,
    name="write",
    description="writes",
    input_schema={},
    annotations={"destructiveHint": True},
    schema_hash="h",
)
CATALOG = ProfileCatalog.builtin()


def pipeline(profile: EndpointProfile) -> ToolChain:
    return ToolChain.for_endpoint(CATALOG.get(profile))


def test_default_profile_keeps_annotations_and_prefixes_the_name():
    presented = pipeline(EndpointProfile.DEFAULT).present(SERVER, TOOL, None)
    assert presented is not None
    assert presented.presented_name == "fs__write"
    assert presented.annotations == {"destructiveHint": True}


def test_write_as_read_profile_reannotates_writes_as_read_safe():
    presented = pipeline(EndpointProfile.WRITE_AS_READ).present(SERVER, TOOL, None)
    assert presented is not None
    assert presented.annotations == {"destructiveHint": False, "readOnlyHint": True}


def test_curation_overrides_win_over_the_profile_and_can_disable():
    curation = BundleTool(
        bundle_id=uuid.uuid4(),
        tool_id=TOOL.id,
        override_name="save",
        override_annotations={"readOnlyHint": None},
    )
    presented = pipeline(EndpointProfile.WRITE_AS_READ).present(SERVER, TOOL, curation)
    assert presented is not None
    assert presented.presented_name == "save"
    assert presented.annotations == {"destructiveHint": False}
    disabled = BundleTool(bundle_id=curation.bundle_id, tool_id=TOOL.id, enabled=False)
    assert pipeline(EndpointProfile.DEFAULT).present(SERVER, TOOL, disabled) is None


def test_ep13_stage_order():
    """Stale and curation filters first, the profile next, the overrides last so they win
    (BND-15, UPS-19)."""
    stages = pipeline(EndpointProfile.WRITE_AS_READ).stages
    assert all(isinstance(s, PresentationStage) for s in stages)
    assert [type(s.stage) for s in stages] == [
        StaleToolFilter,
        CurationFilter,
        ProfileStage,
        OverrideStage,
    ]
    overridden = BundleTool(
        bundle_id=uuid.uuid4(), tool_id=TOOL.id, override_annotations={"readOnlyHint": False}
    )
    presented = pipeline(EndpointProfile.WRITE_AS_READ).present(SERVER, TOOL, overridden)
    assert presented is not None
    assert presented.annotations == {"readOnlyHint": False, "destructiveHint": False}


def test_bnd13_a_disabled_tool_never_reaches_the_profile():
    seen: list[str] = []

    class Recording:
        name = EndpointProfile.DEFAULT
        description = "records"
        warning = None

        def check_auth_modes(self, modes):
            return None

        def transform(self, tool):
            seen.append(tool.presented_name)
            return tool

    disabled = BundleTool(bundle_id=uuid.uuid4(), tool_id=TOOL.id, enabled=False)
    assert ToolChain.for_endpoint(Recording()).present(SERVER, TOOL, disabled) is None
    assert seen == []
