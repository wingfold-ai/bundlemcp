"""What an upstream's ``WWW-Authenticate`` header says about how to authorize."""

import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

_PARAM = re.compile(r'([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^\s,]+))')
INSUFFICIENT_SCOPE = "insufficient_scope"


class UpstreamChallenge(BaseModel):
    """The parts of an authentication challenge the gateway acts on.

    Only the ``Bearer`` scheme carries OAuth meaning; a server that challenges
    with ``Basic`` or a custom scheme wants a credential it cannot discover.
    """

    model_config = ConfigDict(frozen=True)

    scheme: str | None = Field(
        default=None, description="The first challenge's auth scheme, lower-cased"
    )
    resource_metadata: str | None = Field(
        default=None, description="URL of the protected resource document the challenge names"
    )
    scope: list[str] | None = Field(
        default=None, description="Scopes the challenge asks for; None when it names none"
    )
    error: str | None = Field(
        default=None, description="The OAuth error code the challenge carries, if any"
    )

    @classmethod
    def parse(cls, header: str | None) -> Self:
        """Read one header value; an absent or unparseable header yields an empty challenge."""
        if not header or not header.strip():
            return cls()
        scheme = header.strip().split(None, 1)[0].rstrip(",").lower()
        params: dict[str, str] = {}
        for match in _PARAM.finditer(header):
            name = match.group(1).lower()
            value = match.group(2) if match.group(2) is not None else match.group(3)
            params.setdefault(name, value.replace('\\"', '"'))
        scope = params.get("scope")
        return cls(
            scheme=scheme,
            resource_metadata=params.get("resource_metadata"),
            scope=scope.split() if scope is not None else None,
            error=params.get("error"),
        )

    @property
    def names_oauth(self) -> bool:
        """The challenge itself is evidence of OAuth: a Bearer challenge naming its metadata."""
        return self.scheme == "bearer" and self.resource_metadata is not None

    @property
    def is_insufficient_scope(self) -> bool:
        return self.error == INSUFFICIENT_SCOPE
