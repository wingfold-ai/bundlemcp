"""Tiny demo MCP server: a couple of tools incl. an annotated write tool
so a fresh compose install has something to bundle, and the write_as_read profile has
a write tool to re-annotate, plus one that reports progress for the inspector to show.
"""

import asyncio

from fastmcp import Context, FastMCP

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


@mcp.tool
async def countdown(steps: int, ctx: Context) -> str:
    """Count down from steps to zero, reporting progress at each step."""
    for done in range(1, steps + 1):
        await asyncio.sleep(0.3)
        await ctx.report_progress(progress=done, total=steps, message=f"{steps - done} to go")
    return "liftoff"


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",  # noqa: S104
        port=9000,
        path="/mcp",
        # fastmcp >= 3.4.3 rejects non-localhost Host headers unless allowed;
        # the gateway reaches this container by its compose service name.
        allowed_hosts=["echo-mcp", "echo-mcp:9000", "localhost:9100", "127.0.0.1:9100"],
    )
