from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class RegistryHeader(BaseModel):
    """A header a remote in a registry server.json declares, as its publisher wrote it."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str | None = Field(
        default=None, description="Header name; a header without one cannot be offered"
    )
    description: str | None = Field(
        default=None, description="What the value is and where to get it"
    )
    is_required: Annotated[bool, BeforeValidator(bool)] = Field(
        default=False,
        alias="isRequired",
        description="Whether the server needs the header; any truthy value counts",
    )
    is_secret: Annotated[bool, BeforeValidator(bool)] = Field(
        default=False,
        alias="isSecret",
        description="Whether the value is a secret; any truthy value counts",
    )
    value: str | None = Field(
        default=None, description="A value template, such as 'Bearer {api_key}'"
    )
