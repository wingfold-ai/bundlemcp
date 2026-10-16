from pydantic import BaseModel, Field


class ProbedEntry(BaseModel):
    """A prompt or resource as an upstream listed it, before it is cached; never its content."""

    key: str = Field(description="The prompt's name, or the resource's URI")
    name: str = Field(description="Its name as listed; for a prompt the same as the key")
    title: str | None = Field(default=None, description="Display title, when the server set one")
    description: str | None = Field(default=None, description="Description, when set")
