"""The MCP revisions the edge speaks, by era, and handshake-era negotiation (PROT-12).

MCP protocol versions are ``YYYY-MM-DD`` strings, so lexicographic order is
chronological. Modern revisions are named on every request and either match a
registered dialect or are rejected; handshake revisions are negotiated once at
``initialize``.
"""

# Newest first. The head of each list is the era's default.
MODERN_PROTOCOL_VERSIONS = ["2026-07-28"]
HANDSHAKE_PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26"]


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
