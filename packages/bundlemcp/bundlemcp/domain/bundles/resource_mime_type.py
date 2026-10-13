from enum import StrEnum


class ResourceMimeType(StrEnum):
    """The text formats a bundle resource may be written in."""

    # BND-23: text only; binary content is out of scope
    MARKDOWN = "text/markdown"
    PLAIN = "text/plain"
    CSV = "text/csv"
    JSON = "application/json"
    YAML = "application/yaml"
