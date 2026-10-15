"""The MCP conformance suite's server fixtures, served as one upstream.

The suite checks a server through tools, resources and prompts with fixed names
and fixed answers (``test_simple_text``, ``test://static-text``, …). This server
provides them so the suite can run against the gateway with this server as a
bundle member: what the suite then measures is whether the gateway passes each
of them through unchanged. ``tests/conformance/`` wires it up.
"""

import asyncio
import base64
import json

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.prompts import Message
from fastmcp.tools import FunctionTool
from mcp.types import (
    AudioContent,
    EmbeddedResource,
    ImageContent,
    SamplingMessage,
    TextContent,
    TextResourceContents,
)

# the suite checks that $defs and $schema survive listing, so schemas stay as written
mcp = FastMCP("conformance", dereference_schemas=False)

# a 1x1 red pixel
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)
# a 44-byte PCM WAV header with no samples
WAV = base64.b64decode("UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=")


def _png() -> str:
    return base64.b64encode(PNG).decode()


@mcp.tool
def test_simple_text() -> str:
    """Returns a simple text response."""
    return "This is a simple text response for testing."


@mcp.tool
def test_image_content() -> ImageContent:
    """Returns a 1x1 PNG image."""
    return ImageContent(type="image", data=_png(), mimeType="image/png")


@mcp.tool
def test_audio_content() -> AudioContent:
    """Returns a minimal WAV file."""
    return AudioContent(type="audio", data=base64.b64encode(WAV).decode(), mimeType="audio/wav")


@mcp.tool
def test_embedded_resource() -> EmbeddedResource:
    """Returns an embedded text resource."""
    return EmbeddedResource(
        type="resource",
        resource=TextResourceContents(
            uri="test://embedded-resource",
            mimeType="text/plain",
            text="This is an embedded resource content.",
        ),
    )


@mcp.tool
def test_multiple_content_types() -> list[TextContent | ImageContent | EmbeddedResource]:
    """Returns text, an image and an embedded resource."""
    return [
        TextContent(type="text", text="Multiple content types test:"),
        ImageContent(type="image", data=_png(), mimeType="image/png"),
        EmbeddedResource(
            type="resource",
            resource=TextResourceContents(
                uri="test://mixed-content-resource",
                mimeType="application/json",
                text=json.dumps({"test": "data", "value": 123}, separators=(",", ":")),
            ),
        ),
    ]


@mcp.tool
async def test_tool_with_logging(ctx: Context) -> str:
    """Sends three info log messages while it runs."""
    await ctx.info("Tool execution started")
    await asyncio.sleep(0.05)
    await ctx.info("Tool processing data")
    await asyncio.sleep(0.05)
    await ctx.info("Tool execution completed")
    return "Tool with logging executed successfully"


@mcp.tool
async def test_tool_with_progress(ctx: Context) -> str:
    """Reports progress 0, 50 and 100 of 100."""
    for progress in (0, 50, 100):
        await ctx.report_progress(progress=progress, total=100)
        if progress < 100:
            await asyncio.sleep(0.05)
    return "Tool with progress executed successfully"


@mcp.tool
def test_error_handling() -> str:
    """Always fails."""
    raise ToolError("This tool intentionally returns an error for testing")


@mcp.tool
async def test_sampling(prompt: str, ctx: Context) -> str:
    """Asks the client's model to answer the prompt."""
    result = await ctx.session.create_message(
        [SamplingMessage(role="user", content=TextContent(type="text", text=prompt))],
        max_tokens=100,
    )
    text = result.content.text if isinstance(result.content, TextContent) else str(result.content)
    return f"LLM response: {text}"


@mcp.tool
async def test_elicitation(message: str, ctx: Context) -> str:
    """Asks the user for a username and an email address."""
    result = await ctx.session.elicit(
        message=message,
        requested_schema={
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "User's response"},
                "email": {"type": "string", "description": "User's email address"},
            },
            "required": ["username", "email"],
        },
    )
    return f"User response: action={result.action}, content={json.dumps(result.content)}"


@mcp.tool
async def test_elicitation_sep1034_defaults(ctx: Context) -> str:
    """Asks for input whose every field has a default."""
    result = await ctx.session.elicit(
        message="Please review and update the form fields with defaults",
        requested_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "User name", "default": "John Doe"},
                "age": {"type": "integer", "description": "User age", "default": 30},
                "score": {"type": "number", "description": "User score", "default": 95.5},
                "status": {
                    "type": "string",
                    "description": "User status",
                    "enum": ["active", "inactive", "pending"],
                    "default": "active",
                },
                "verified": {"type": "boolean", "description": "Verified", "default": True},
            },
        },
    )
    return f"Elicitation completed: action={result.action}, content={json.dumps(result.content)}"


@mcp.tool
async def test_elicitation_sep1330_enums(ctx: Context) -> str:
    """Asks for input with every kind of enum."""
    result = await ctx.session.elicit(
        message="Please select options from the enum fields",
        requested_schema={
            "type": "object",
            "properties": {
                "untitledSingle": {"type": "string", "enum": ["option1", "option2", "option3"]},
                "titledSingle": {
                    "type": "string",
                    "oneOf": [
                        {"const": "value1", "title": "First Option"},
                        {"const": "value2", "title": "Second Option"},
                        {"const": "value3", "title": "Third Option"},
                    ],
                },
                "legacyEnum": {
                    "type": "string",
                    "enum": ["opt1", "opt2", "opt3"],
                    "enumNames": ["Option One", "Option Two", "Option Three"],
                },
                "untitledMulti": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["option1", "option2", "option3"]},
                },
                "titledMulti": {
                    "type": "array",
                    "items": {
                        "anyOf": [
                            {"const": "value1", "title": "First Choice"},
                            {"const": "value2", "title": "Second Choice"},
                            {"const": "value3", "title": "Third Choice"},
                        ]
                    },
                },
            },
        },
    )
    return f"Elicitation completed: action={result.action}, content={json.dumps(result.content)}"


def json_schema_2020_12_tool(name: str | None = None, address: dict | None = None) -> str:
    """Tool with JSON Schema 2020-12 features"""
    return f"name={name}, address={address}"


mcp.add_tool(
    FunctionTool.from_function(json_schema_2020_12_tool).model_copy(
        update={
            "parameters": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "$defs": {
                    "address": {
                        "type": "object",
                        "properties": {
                            "street": {"type": "string"},
                            "city": {"type": "string"},
                        },
                    }
                },
                "properties": {
                    "name": {"type": "string"},
                    "address": {"$ref": "#/$defs/address"},
                },
                "additionalProperties": False,
            }
        }
    )
)


@mcp.resource(
    "test://static-text", mime_type="text/plain", description="A static text resource for testing"
)
def static_text() -> str:
    return "This is the content of the static text resource."


@mcp.resource(
    "test://static-binary", mime_type="image/png", description="A static binary resource (PNG)"
)
def static_binary() -> bytes:
    return PNG


@mcp.resource(
    "test://watched-resource",
    mime_type="text/plain",
    description="A resource clients may subscribe to",
)
def watched_resource() -> str:
    return "Watched resource content."


@mcp.resource(
    "test://template/{id}/data",
    mime_type="application/json",
    description="A resource template with an id parameter",
)
def template_data(id: str) -> str:
    return json.dumps(
        {"id": id, "templateTest": True, "data": f"Data for ID: {id}"}, separators=(",", ":")
    )


@mcp.prompt
def test_prompt_with_embedded_resource(resourceUri: str) -> list[Message]:  # noqa: N803
    """A prompt that embeds a resource."""
    return [
        Message(
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri=resourceUri,
                    mimeType="text/plain",
                    text="Embedded resource content for testing.",
                ),
            )
        ),
        Message("Please process the embedded resource above."),
    ]


@mcp.prompt
def test_prompt_with_image() -> list[Message]:
    """A prompt that carries an image."""
    return [
        Message(ImageContent(type="image", data=_png(), mimeType="image/png")),
        Message("Please analyze the image above."),
    ]


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",  # noqa: S104
        port=9000,
        path="/mcp",
        # the gateway reaches this container by its compose service name
        allowed_hosts=["conformance-mcp", "conformance-mcp:9000"],
    )
