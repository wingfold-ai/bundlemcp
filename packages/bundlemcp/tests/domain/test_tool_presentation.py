"""How curation and the endpoint profile shape the tool a client sees (PROF-3, TM-2/3/4)."""

import uuid

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.tool_presentation import present_tool
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
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


def test_default_profile_keeps_annotations_and_prefixes_the_name():
    presented = present_tool(SERVER, TOOL, None, EndpointProfile.DEFAULT)
    assert presented is not None
    assert presented.presented_name == "fs__write"
    assert presented.annotations == {"destructiveHint": True}


def test_chatgpt_profile_reannotates_writes_as_read_safe():
    presented = present_tool(SERVER, TOOL, None, EndpointProfile.CHATGPT)
    assert presented is not None
    assert presented.annotations == {"destructiveHint": False, "readOnlyHint": True}


def test_curation_overrides_win_over_the_profile_and_can_disable():
    curation = BundleTool(
        bundle_id=uuid.uuid4(),
        tool_id=TOOL.id,
        override_name="save",
        override_annotations={"readOnlyHint": None},
    )
    presented = present_tool(SERVER, TOOL, curation, EndpointProfile.CHATGPT)
    assert presented is not None
    assert presented.presented_name == "save"
    assert presented.annotations == {"destructiveHint": False}
    disabled = BundleTool(bundle_id=curation.bundle_id, tool_id=TOOL.id, enabled=False)
    assert present_tool(SERVER, TOOL, disabled, EndpointProfile.DEFAULT) is None
