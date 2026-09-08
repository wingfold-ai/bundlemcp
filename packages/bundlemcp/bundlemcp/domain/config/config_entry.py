from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.domain.shared.clock import utcnow


class ConfigEntry(BaseModel):
    """Runtime-tunable key/value settings."""

    key: str = Field(description="Name of the setting")
    value: Any = Field(
        default=None,
        description="Stored value; its type comes from the key's declared default",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        description="When the value was last changed",
    )
