from enum import StrEnum


class ImportOutcome(StrEnum):
    """What importing one resource did, or would do on a dry run."""

    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"
