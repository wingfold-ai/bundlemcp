from enum import StrEnum


class AuditKind(StrEnum):
    """What an audit record is about: a tool call through an endpoint, or a management action."""

    TOOL_CALL = "tool_call"
    MANAGEMENT = "management"
