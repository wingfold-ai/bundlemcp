from enum import StrEnum


class EndpointProfile(StrEnum):
    DEFAULT = "default"
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
