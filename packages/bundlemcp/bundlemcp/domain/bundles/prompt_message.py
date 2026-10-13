from typing import Self

from pydantic import BaseModel, Field, model_validator

from bundlemcp.domain.bundles.prompt_role import PromptRole
from bundlemcp.domain.bundles.prompt_template import placeholders
from bundlemcp.domain.shared.resource_names import BundleResourceName


class PromptMessage(BaseModel):
    """One message of a bundle prompt: either text, or one of the bundle's resources."""

    role: PromptRole = Field(description="Who speaks the message: 'user' or 'assistant'")
    text: str | None = Field(  # BPR-3
        default=None,
        description="Message text; may refer to the prompt's arguments as {{argument}}. "
        "Set exactly one of 'text' and 'resource'",
    )
    resource: BundleResourceName | None = Field(  # BPR-3
        default=None,
        description="Name of a resource of the same bundle, embedded in full when the prompt "
        "is rendered. Set exactly one of 'text' and 'resource'",
    )

    @model_validator(mode="after")
    def _one_kind_of_content(self) -> Self:
        if (self.text is None) == (self.resource is None):
            raise ValueError("a prompt message has either 'text' or 'resource', not both")
        return self

    @property
    def placeholders(self) -> set[str]:
        """The argument names this message's text refers to."""
        return placeholders(self.text) if self.text is not None else set()
