from datetime import datetime

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead
from bundlemcp.domain.bundles.prompt_argument import PromptArgument
from bundlemcp.domain.bundles.prompt_message import PromptMessage


class BundlePromptRead(EntityRead):
    """A prompt the bundle itself serves, as stored."""

    name: str = Field(description="Prompt name, as clients see it")
    title: str | None = Field(description="Human-readable title")
    description: str | None = Field(description="What the prompt is for")
    arguments: list[PromptArgument] = Field(description="Arguments the prompt takes")
    messages: list[PromptMessage] = Field(description="Messages of the prompt, in order")
    created_at: datetime = Field(description="When the prompt was created")
    updated_at: datetime = Field(description="When the prompt was last changed")
