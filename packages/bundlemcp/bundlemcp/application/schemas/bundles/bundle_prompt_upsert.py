from pydantic import BaseModel, Field

from bundlemcp.domain.bundles.prompt_argument import PromptArgument
from bundlemcp.domain.bundles.prompt_message import PromptMessage
from bundlemcp.domain.shared.resource_names import PromptName


class BundlePromptUpsert(BaseModel):
    """Body for creating or replacing a prompt the bundle itself serves.

    Not secret: the prompt is served to every caller of every endpoint of the
    bundle, and to the model.
    """

    name: PromptName = Field(  # BPR-2
        description="Prompt name, unique in the bundle: letters, digits, underscores and "
        "hyphens, never '__'. Clients see it unprefixed, unlike a member server's prompts"
    )
    title: str | None = Field(default=None, description="Human-readable title")
    description: str | None = Field(
        default=None, description="What the prompt is for, shown when a user picks a prompt"
    )
    arguments: list[PromptArgument] = Field(  # BPR-1
        default_factory=list,
        description="Arguments the prompt takes; each message text may refer to one as {{name}}",
    )
    messages: list[PromptMessage] = Field(  # BPR-1, BPR-3, BPR-17
        min_length=1,
        description="Messages of the prompt, in conversation order; together at most 64 KiB "
        "of text. Not secret: served to every caller of the bundle and to the model",
    )
