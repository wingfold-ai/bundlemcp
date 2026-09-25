from pydantic import BaseModel, Field


class ServerJsonHeader(BaseModel):
    """A header a registry server.json says a remote needs."""

    name: str = Field(description="Header name, such as 'X-API-Key' or 'Authorization'")
    description: str | None = Field(
        default=None, description="What the value is and where to get it, from the publisher"
    )
    is_required: bool = Field(default=False, description="Whether the server needs it")
    is_secret: bool = Field(
        default=False, description="Whether the value is a secret to enter in a masked field"
    )
    value: str | None = Field(
        default=None,
        description="A value template from the document, such as 'Bearer {api_key}', when it "
        "gives one",
    )
