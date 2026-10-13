from pydantic import BaseModel, Field

from bundlemcp.domain.bundles.prompt_argument import PromptArgument
from bundlemcp.domain.shared.resource_names import PromptName


class PromptListing(BaseModel):
    """What a client learns about a bundle prompt before asking for it: everything but its
    messages."""

    name: PromptName = Field(  # BND-19
        description="Prompt name, unique in its bundle: letters, digits, underscores and "
        "single hyphens, never '__'"
    )
    title: str | None = Field(default=None, description="Human-readable title")
    description: str | None = Field(default=None, description="What the prompt is for")
    arguments: list[PromptArgument] = Field(  # BND-18
        default_factory=list, description="Arguments the prompt takes, in display order"
    )

    def argument(self, name: str) -> PromptArgument | None:
        """The declared argument with this name, or None."""
        return next((argument for argument in self.arguments if argument.name == name), None)

    def missing_arguments(self, supplied: dict[str, str]) -> list[str]:
        """The required arguments the caller did not supply, in declaration order."""
        return [a.name for a in self.arguments if a.required and a.name not in supplied]

    @property
    def offers_completions(self) -> bool:
        """Whether any argument has suggested values to complete from."""
        return any(argument.values for argument in self.arguments)
