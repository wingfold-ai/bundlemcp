from dataclasses import dataclass
from typing import Any


@dataclass
class _CallOutcome:
    status: str  # "success" | "error"
    result: Any = None  # mcp CallToolResult on success
    error_message: str | None = None
    code: int | None = None
