from enum import StrEnum


class PromptRole(StrEnum):
    """Who speaks a prompt message, in MCP's vocabulary."""

    USER = "user"
    ASSISTANT = "assistant"
