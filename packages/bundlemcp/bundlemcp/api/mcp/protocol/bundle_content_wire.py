"""A bundle's own prompts and resources in the MCP wire shapes."""

from typing import Any

from mcp import types
from pydantic import BaseModel

from bundlemcp.domain.bundles.bundle_resource import BundleResource
from bundlemcp.domain.bundles.prompt_listing import PromptListing
from bundlemcp.domain.bundles.prompt_message import PromptMessage
from bundlemcp.domain.bundles.resource_listing import ResourceListing


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(by_alias=True, mode="json", exclude_none=True)


def prompt_entry(prompt: PromptListing) -> dict[str, Any]:
    """A ``prompts/list`` entry; the name is the bundle's own, never prefixed."""
    return _dump(
        types.Prompt(
            name=prompt.name,
            title=prompt.title,
            description=prompt.description,
            arguments=[
                types.PromptArgument(
                    name=argument.name,
                    description=argument.description,
                    required=argument.required,
                )
                for argument in prompt.arguments
            ],
        )
    )


def resource_entry(resource: ResourceListing) -> dict[str, Any]:
    """A ``resources/list`` entry."""
    return _dump(
        types.Resource(
            uri=resource.uri,
            name=resource.name,
            title=resource.title,
            description=resource.description,
            mimeType=resource.mime_type,
            size=resource.size_bytes,
        )
    )


def resource_contents(resource: BundleResource) -> dict[str, Any]:
    """The text contents ``resources/read`` and an embedding prompt both carry."""
    return _dump(
        types.TextResourceContents(
            uri=resource.uri, mimeType=resource.mime_type, text=resource.content
        )
    )


def prompt_message(
    message: PromptMessage, resources: dict[str, BundleResource]
) -> dict[str, Any] | None:
    """One rendered message; a resource message embeds the resource whole.

    None for a resource message whose resource no longer exists, which only a
    concurrent delete can cause.
    """
    if message.text is not None:
        content: dict[str, Any] = _dump(types.TextContent(type="text", text=message.text))
    elif (resource := resources.get(message.resource or "")) is not None:
        content = {"type": "resource", "resource": resource_contents(resource)}
    else:
        return None
    return {"role": str(message.role), "content": content}
