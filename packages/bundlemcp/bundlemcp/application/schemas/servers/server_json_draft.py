from pydantic import BaseModel, Field

from bundlemcp.application.schemas.servers.server_json_header import ServerJsonHeader


class ServerJsonDraft(BaseModel):
    """A registration drafted from a registry server.json, for an operator to complete."""

    name: str = Field(description="A slug-safe server name derived from the document's name")
    description: str | None = Field(
        default=None, description="The document's description of the server"
    )
    url: str | None = Field(
        default=None,
        description="The first streamable-http remote's URL; null when the document has none",
    )
    url_variables: list[str] = Field(
        default=[],
        description="Names of {placeholders} in the URL the operator must fill in first",
    )
    headers: list[ServerJsonHeader] = Field(
        default=[], description="Headers the remote declares, in the document's order"
    )
    website_url: str | None = Field(default=None, description="The document's website URL")
    problems: list[str] = Field(
        default=[],
        description="Why parts of the document could not be used, such as an sse-only remote",
    )
