from pydantic import BaseModel, Field

from bundlemcp.domain.shared.resource_names import ResourceName


class PromptArgument(BaseModel):
    """One argument a bundle prompt takes, referred to in its text as ``{{name}}``."""

    name: ResourceName = Field(
        description="Argument name: letters, digits, underscores and hyphens"
    )
    description: str | None = Field(
        default=None, description="What the argument is for, shown to the user filling it in"
    )
    required: bool = Field(  # BND-21
        default=False,
        description="Whether the prompt refuses to render without it; an optional argument "
        "left out is replaced with the empty string",
    )
    values: list[str] = Field(  # BND-22
        default_factory=list,
        description="Suggested values a client offers as completions, in this order; empty "
        "when the argument is free text",
    )

    def completions(self, partial: str) -> list[str]:
        """The suggested values that start with what the user typed so far, ignoring case."""
        prefix = partial.casefold()
        return [value for value in self.values if value.casefold().startswith(prefix)]
