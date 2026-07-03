"""Tiny demo MCP server: a couple of tools incl. an annotated write tool
so a fresh compose install has something to bundle, and the chatgpt profile has
a write tool to re-annotate.
"""

from fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool
def echo(text: str) -> str:
    """Return the text unchanged."""
    return text


@mcp.tool
def reverse(text: str) -> str:
    """Return the text reversed."""
    return text[::-1]


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
def shout(text: str) -> str:
    """Uppercase the text (declared as a write/destructive tool for demo purposes)."""
    return text.upper()


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9000, path="/mcp")  # noqa: S104
