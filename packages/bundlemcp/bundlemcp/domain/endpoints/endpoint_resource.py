"""The URL that identifies an endpoint as an OAuth protected resource."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

# RFC 9728 section 3: the well-known segment is inserted between the host and
# the resource's own path, so each endpoint has its own metadata document.
PROTECTED_RESOURCE_WELL_KNOWN = "/.well-known/oauth-protected-resource"


class EndpointResource(BaseModel):
    """The canonical resource identifier of one endpoint (RFC 8707).

    Every place that writes the identifier — discovery metadata, the 401
    challenge, token audiences, the URL shown to users — and the one place
    that reads it back, the ``resource`` parameter of an authorization
    request, agree on its shape through this object.
    """

    model_config = ConfigDict(frozen=True)

    PATH_SUFFIX: ClassVar[str] = "/mcp"

    public_base: str = Field(description="The gateway's public URL without a trailing slash")
    endpoint_name: str = Field(description="Name of the endpoint the resource identifies")

    @property
    def url(self) -> str:
        """The identifier itself: the endpoint's MCP URL under the public base."""
        return f"{self.public_base}/{self.endpoint_name}{self.PATH_SUFFIX}"

    @property
    def metadata_url(self) -> str:
        """Where the resource's protected-resource metadata document is served."""
        return (
            f"{self.public_base}{PROTECTED_RESOURCE_WELL_KNOWN}"
            f"/{self.endpoint_name}{self.PATH_SUFFIX}"
        )

    @classmethod
    def parse(cls, public_base: str, resource: str) -> "EndpointResource | None":
        """Read an identifier back; None when it does not name an endpoint of this gateway."""
        prefix = public_base + "/"
        if not resource.startswith(prefix) or not resource.endswith(cls.PATH_SUFFIX):
            return None
        name = resource[len(prefix) : -len(cls.PATH_SUFFIX)]
        if not name or "/" in name:
            return None
        return cls(public_base=public_base, endpoint_name=name)
