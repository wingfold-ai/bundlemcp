"""How the gateway settles the MCP revision it speaks with an upstream server."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field


class NegotiationMode(StrEnum):
    """How the MCP revision is chosen when the gateway connects, rather than pinned: 'auto'
    probes server/discover and falls back to the initialize handshake; 'session' always uses
    the handshake and the session it opens."""

    AUTO = "auto"
    """Probe ``server/discover`` and fall back to the ``initialize`` handshake."""

    SESSION = "session"
    """Always use the ``initialize`` handshake and the session it opens."""


PinnedRevision = Annotated[
    str,
    Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="An MCP revision date, such as '2026-07-28', spoken without negotiation",
    ),
]

ProtocolMode = NegotiationMode | PinnedRevision
"""A negotiation mode, or a pinned revision date."""
