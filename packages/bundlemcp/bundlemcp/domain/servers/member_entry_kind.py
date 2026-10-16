from enum import StrEnum


class MemberEntryKind(StrEnum):
    """Which of a member's listings an entry comes from."""

    PROMPT = "prompt"
    RESOURCE = "resource"
