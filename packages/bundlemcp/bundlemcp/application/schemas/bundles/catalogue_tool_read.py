from pydantic import BaseModel, Field


class CatalogueToolRead(BaseModel):
    """A tool as a client will see it, for someone deciding whether to connect a bundle."""

    name: str = Field(
        description="Name the client sees and calls, already prefixed with its server and "
        "with any per-bundle rename applied"
    )
    title: str | None = Field(
        description="Human-readable title for the tool, when the server or the administrator "
        "provided one"
    )
    description: str | None = Field(
        description="What the tool does, as the model calling it is told; absent when the "
        "server published none"
    )
    server_name: str = Field(description="Upstream server that provides the tool")
