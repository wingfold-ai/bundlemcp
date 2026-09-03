from typing import Any

from pydantic import BaseModel, Field


class ConfigEntryRead(BaseModel):
    """One runtime-tunable setting after a change."""

    key: str = Field(description="Name of the setting")
    value: Any = Field(description="The value now in effect, in the type the key declares")
