"""Protocol-version negotiation for the client-facing edge (PROT-12).

MCP protocol versions are `YYYY-MM-DD` strings, so lexicographic order is
chronological. The gateway declares a supported window and negotiates the best
version common with the client; a request older than the window fails
`initialize` rather than degrading silently. The proxied message types
(tools/prompts/resources/completions) are wire-compatible across this window, so
translation is currently an identity pass-through — `translate` is the seam where
a shape rule lands if the window ever widens to an incompatible revision.
"""

# Newest first. The active default is the head of this list.
SUPPORTED_PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26"]
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]
_OLDEST = SUPPORTED_PROTOCOL_VERSIONS[-1]


def negotiate_version(requested: str | None) -> str | None:
    """Pick the version to serve the client, or None if there is no overlap.

    - no/blank request → the latest supported version;
    - exactly supported → that version;
    - newer than we know → our latest (client decides whether to proceed);
    - within the window but not exact → the highest supported ≤ requested;
    - older than the whole window → None (caller fails `initialize`).
    """
    if not requested:
        return LATEST_PROTOCOL_VERSION
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    if requested > LATEST_PROTOCOL_VERSION:
        return LATEST_PROTOCOL_VERSION
    if requested < _OLDEST:
        return None
    return next(v for v in SUPPORTED_PROTOCOL_VERSIONS if v <= requested)


def translate(message: dict, from_version: str, to_version: str) -> dict:
    """Reshape a proxied message between two negotiated versions.

    Identity within the current window (the proxied message types are
    compatible). Kept as the extension point for a future incompatible revision.
    """
    return message
