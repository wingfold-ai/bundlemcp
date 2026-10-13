from pydantic import BaseModel, Field

from bundlemcp.domain.bundles.bundle_resource import BundleResource
from bundlemcp.domain.bundles.prompt_message import PromptMessage


class RenderedPrompt(BaseModel):
    """A bundle prompt with its arguments substituted and the resources it embeds."""

    description: str | None = Field(description="What the prompt is for")
    messages: list[PromptMessage] = Field(description="Messages with placeholders replaced")
    resources: dict[str, BundleResource] = Field(
        description="Every resource a message embeds, by name"
    )
