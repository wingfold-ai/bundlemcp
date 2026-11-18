"""What a change of a server's URL moves away from."""

from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.upstream_oauth.resource_indicator import canonical_resource

DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    return scheme, (parsed.hostname or "").lower(), parsed.port or DEFAULT_PORTS.get(scheme)


class UrlChange(BaseModel):
    """A server's URL before and after a write.

    Tokens belong to the resource they were requested for, so any change of the
    canonical resource matters to them; secrets an admin entered belong to the
    host they were entered for, so only a change of origin matters to those.
    """

    model_config = ConfigDict(frozen=True)

    previous: str = Field(description="The URL the server had before the write")
    current: str = Field(description="The URL the write gives the server")

    @property
    def moves_resource(self) -> bool:
        """The URL names another resource: scheme, host, port or path differ."""
        return canonical_resource(self.previous) != canonical_resource(self.current)

    @property
    def moves_origin(self) -> bool:
        """The URL is on another origin: scheme, host or port differ."""
        return _origin(self.previous) != _origin(self.current)
