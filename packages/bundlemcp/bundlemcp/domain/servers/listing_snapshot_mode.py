from enum import StrEnum


class ListingSnapshotMode(StrEnum):
    """Whether a server's prompt and resource listings are served from its discovery snapshot."""

    AUTO = "auto"
    SHARED = "shared"
    LIVE = "live"
