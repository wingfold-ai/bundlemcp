"""The MCP revisions the edge speaks, by era, and handshake-era negotiation.

The revision lists come from the MCP SDK's own registry, so a new revision the
SDK learns is served here without a table edit. The one decision that is the
gateway's is the floor of the handshake window: revisions older than it are
never negotiated, however long the SDK keeps them.
"""

# Handshake negotiation, and the revisions tracked from the SDK.

import mcp_types.version as sdk_versions
from mcp_types.version import is_version_at_least

OLDEST_HANDSHAKE_SERVED = "2025-03-26"  # the handshake era starts here

# Newest first. The head of each list is the era's default.
MODERN_PROTOCOL_VERSIONS = list(reversed(sdk_versions.MODERN_PROTOCOL_VERSIONS))
HANDSHAKE_PROTOCOL_VERSIONS = [
    v
    for v in reversed(sdk_versions.HANDSHAKE_PROTOCOL_VERSIONS)
    if is_version_at_least(v, OLDEST_HANDSHAKE_SERVED)
]


def negotiate_handshake_version(requested: str | None, supported: list[str]) -> str | None:
    """Pick the handshake version to serve the client, or None if there is no overlap.

    ``supported`` is newest first. Rules:

    - no/blank request → the newest supported version;
    - exactly supported → that version;
    - newer than we know → our newest (client decides whether to proceed);
    - within the window but not exact → the newest supported ≤ requested;
    - older than the whole window, or nothing supported → None (caller fails
      ``initialize``).
    """
    if not supported:
        return None
    newest, oldest = supported[0], supported[-1]
    if not requested:
        return newest
    if requested in supported:
        return requested
    if requested > newest:
        return newest
    if requested < oldest:
        return None
    return next(v for v in supported if v <= requested)
