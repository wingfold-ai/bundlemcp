from enum import StrEnum


class ClientIdentification(StrEnum):
    """How the gateway identifies itself to an upstream authorization server.

    Listed in the MCP authorization spec's priority order after a client an
    admin stored, which always wins.
    """

    PREREGISTERED = "preregistered"  # an admin stored a client id
    METADATA_DOCUMENT = "metadata_document"  # the gateway's own client metadata URL is its id
    DYNAMIC_REGISTRATION = "dynamic_registration"  # RFC 7591, deprecated by MCP 2026-07-28
    PREREGISTERED_REQUIRED = "preregistered_required"  # nothing automatic is offered
