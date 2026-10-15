"""The path shape of the MCP endpoints, for middleware that runs before routing."""

import re

MCP_PATH = re.compile(r"^/[^/]+/mcp/?$")
