"""The name a bundle presents an upstream tool or prompt under."""

from pydantic import BaseModel, ConfigDict, Field

PRESENTED_NAME_SEPARATOR = "__"  # separates the server prefix from the upstream name


class PresentedName(BaseModel):
    """`server__name`: the upstream name qualified by the member server it belongs to.

    Server names may not contain the separator, so splitting on the first
    occurrence always recovers both parts.
    """

    model_config = ConfigDict(frozen=True)

    server: str = Field(description="Member server that owns the upstream object")
    name: str = Field(description="Name as the upstream server reports it")

    @property
    def text(self) -> str:
        return f"{self.server}{PRESENTED_NAME_SEPARATOR}{self.name}"

    @classmethod
    def parse(cls, text: str) -> PresentedName | None:
        """Split a presented name; None when it carries no server prefix."""
        server, separator, name = text.partition(PRESENTED_NAME_SEPARATOR)
        if not separator or not server or not name:
            return None
        return cls(server=server, name=name)

    @classmethod
    def for_tool(cls, server: str, name: str, override: str | None) -> str:
        """The client-visible name: a curation override when set, else the prefixed name."""
        return override if override else cls(server=server, name=name).text
